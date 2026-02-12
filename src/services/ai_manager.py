"""
AI 调度中心 - 双模型两阶段推理流程
"""
import asyncio
import time
from collections import deque
from typing import Optional, List, Dict, Any
from src.core.config_manager import ConfigManager
from src.core.logger import logger
from src.core.model_logger import get_model_logger
from src.services.http_client import AsyncHTTPClient
from src.models.api_types import ChatMessage


class AIManager:
    """
    AI 调度管理器（单例）
    
    双阶段推理流程：
    1. 场景整理 (Organize Context): 分析用户消息，提取关键信息
    2. 回复生成 (Generate Reply): 基于场景摘要和角色设定，生成最终回复
    """
    
    _instance: Optional['AIManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.config = None
        # 短期对话内存：{user_id: deque([(query, reply), ...])}
        self._short_term_memory: Dict[str, deque] = {}
        self._max_short_term_rounds = 100  # 缓存最多 100 轮对话（用于存储）
        self._bot_qq_id: Optional[str] = None  # Bot 的 QQ 号，用于识别自己的消息
        logger.info("✅ AI Manager initialized (dual-stage reasoning mode)")
    
    async def load_history_from_napcat(self, bot, user_id: str, count: int = 200) -> int:
        """
        从 NapCat 加载私聊历史消息到短期内存
        
        Args:
            bot: NoneBot Bot 实例
            user_id: 用户 QQ 号
            count: 拉取消息数量（默认 200 条，尽可能多地加载历史）
            
        Returns:
            加载的对话轮数
        """
        try:
            # 获取 Bot 自己的 QQ 号
            if not self._bot_qq_id:
                bot_info = await bot.get_login_info()
                self._bot_qq_id = str(bot_info.get("user_id", ""))
            
            # 调用 NapCat API 获取私聊历史
            logger.debug(f"📥 请求加载 {count} 条历史消息: user={user_id}")
            history = await bot.get_friend_msg_history(user_id=int(user_id), count=count)
            messages = history.get("messages", [])
            
            if not messages:
                logger.debug(f"   未获取到历史消息")
                return 0
            
            logger.debug(f"   获取到 {len(messages)} 条原始消息")
            
            # 按时间排序（从旧到新）
            messages.sort(key=lambda m: m.get("time", 0))
            
            # 解析消息，配对 Q&A
            pairs = []
            pending_query = None
            skipped_commands = 0
            skipped_empty = 0
            
            for msg in messages:
                sender_id = str(msg.get("sender", {}).get("user_id", ""))
                # 提取纯文本内容
                text = ""
                for seg in msg.get("message", []):
                    if seg.get("type") == "text":
                        text += seg.get("data", {}).get("text", "")
                
                text = text.strip()
                if not text:
                    skipped_empty += 1
                    continue
                
                # 跳过命令消息（以 / 开头）
                if text.startswith("/"):
                    pending_query = None  # 重置，避免命令回复被配对
                    skipped_commands += 1
                    continue
                
                if sender_id == self._bot_qq_id:
                    # Bot 的消息
                    if pending_query:
                        pairs.append((pending_query, text))
                        pending_query = None
                else:
                    # 用户的消息
                    # 如果有未配对的查询，说明用户连续发了多条，只保留最新的
                    if pending_query:
                        logger.debug(f"   用户连续消息，丢弃: {pending_query[:30]}")
                    pending_query = text
            
            logger.debug(f"   配对结果: {len(pairs)} 轮对话, 跳过命令 {skipped_commands} 条, 跳过空消息 {skipped_empty} 条")
            
            # 存入短期内存
            if pairs:
                if user_id not in self._short_term_memory:
                    self._short_term_memory[user_id] = deque(maxlen=self._max_short_term_rounds)
                
                # 只取最近的 N 轮
                for query, reply in pairs[-self._max_short_term_rounds:]:
                    self._short_term_memory[user_id].append((query, reply))
                
                logger.info(f"📥 从 NapCat 加载 {len(pairs)} 轮历史对话（存入 {min(len(pairs), self._max_short_term_rounds)} 轮）: user={user_id}")
            
            return len(pairs)
            
        except Exception as e:
            logger.warning(f"从 NapCat 加载历史失败: {e}")
            return 0
    
    async def load_group_history_from_napcat(self, bot, group_id: str, user_id: str, count: int = 300) -> int:
        """
        从 NapCat 加载群聊历史消息（筛选特定用户）
        
        Args:
            bot: NoneBot Bot 实例
            group_id: 群号
            user_id: 用户 QQ 号
            count: 拉取消息数量（默认 300 条，群聊消息多，需要更多才能配对出足够的对话）
            
        Returns:
            加载的对话轮数
        """
        try:
            # 获取 Bot 自己的 QQ 号
            if not self._bot_qq_id:
                bot_info = await bot.get_login_info()
                self._bot_qq_id = str(bot_info.get("user_id", ""))
            
            # 调用 NapCat API 获取群聊历史
            logger.debug(f"📥 请求加载 {count} 条群聊历史: group={group_id}, user={user_id}")
            history = await bot.get_group_msg_history(group_id=int(group_id), count=count)
            messages = history.get("messages", [])
            
            if not messages:
                logger.debug(f"   未获取到历史消息")
                return 0
            
            logger.debug(f"   获取到 {len(messages)} 条原始消息")
            
            # 按时间排序（从旧到新）
            messages.sort(key=lambda m: m.get("time", 0))
            
            # 解析消息，只关注目标用户和 Bot 的对话
            pairs = []
            pending_query = None
            skipped_other_users = 0
            skipped_commands = 0
            skipped_empty = 0
            
            for msg in messages:
                sender_id = str(msg.get("sender", {}).get("user_id", ""))
                
                # 提取纯文本内容
                text = ""
                for seg in msg.get("message", []):
                    if seg.get("type") == "text":
                        text += seg.get("data", {}).get("text", "")
                
                text = text.strip()
                if not text:
                    skipped_empty += 1
                    continue
                
                # 跳过命令消息（以 / 开头）
                if text.startswith("/"):
                    pending_query = None  # 重置，避免命令回复被配对
                    skipped_commands += 1
                    continue
                
                if sender_id == self._bot_qq_id:
                    # Bot 的消息，如果前面有该用户的消息，配对
                    if pending_query:
                        pairs.append((pending_query, text))
                        pending_query = None
                elif sender_id == user_id:
                    # 目标用户的消息
                    # 如果有未配对的查询，说明用户连续发了多条，只保留最新的
                    if pending_query:
                        logger.debug(f"   用户连续消息，丢弃: {pending_query[:30]}")
                    pending_query = text
                else:
                    # 其他人的消息，重置 pending
                    if pending_query:
                        skipped_other_users += 1
                    pending_query = None
            
            logger.debug(f"   配对结果: {len(pairs)} 轮对话, 跳过其他用户 {skipped_other_users} 条, 跳过命令 {skipped_commands} 条, 跳过空消息 {skipped_empty} 条")
            
            # 存入短期内存
            if pairs:
                if user_id not in self._short_term_memory:
                    self._short_term_memory[user_id] = deque(maxlen=self._max_short_term_rounds)
                
                # 只取最近的 N 轮
                for query, reply in pairs[-self._max_short_term_rounds:]:
                    self._short_term_memory[user_id].append((query, reply))
                
                logger.info(f"📥 从 NapCat 加载 {len(pairs)} 轮群聊历史（存入 {min(len(pairs), self._max_short_term_rounds)} 轮）: group={group_id}, user={user_id}")
            
            return len(pairs)
            
        except Exception as e:
            logger.warning(f"从 NapCat 加载群聊历史失败: {e}")
            return 0
    
    def has_short_term_memory(self, user_id: str) -> bool:
        """检查用户是否有短期内存"""
        return user_id in self._short_term_memory and len(self._short_term_memory[user_id]) > 0
    
    def _refresh_config(self) -> None:
        try:
            self.config = ConfigManager.get_ai_config()
        except RuntimeError:
            logger.warning("Config not loaded, please call ConfigManager.load()")
    
    async def chat(
        self,
        user_message: str,
        user_name: str = "用户",
        user_id: str = None,
        group_id: str = None,
        group_name: str = None
    ) -> str:
        """
        Handle chat request - dual-stage pipeline (增强版：支持 RAG + 好感度)
        
        Args:
            user_message: User message
            user_name: User name (default: "用户")
            user_id: User ID (用于检索长期记忆和存储对话)
            group_id: Group ID (群聊时传入)
            group_name: Group name (群聊时传入)
            
        Returns:
            AI reply text
        """
        try:
            if self.config is None:
                self._refresh_config()
            
            # === 输入清洗：检测并过滤注入话术 ===
            from src.core.persona_guard import detect_injection, clean_injection
            is_injection, _ = detect_injection(user_message)
            if is_injection:
                user_message = clean_injection(user_message)
            
            # === 预先检索知识库和长期记忆 ===
            from src.services.vector_service import get_vector_service
            vector_service = get_vector_service()
            
            # 检索知识库
            kb_info_raw = vector_service.search_knowledge(user_message)
            kb_stats = getattr(vector_service, '_last_kb_search_stats', {})
            
            # 格式化知识库信息（包含检索统计，用于日志和调试）
            if kb_info_raw:
                logger.info(f"📚 [知识库] 命中 {len(kb_info_raw)} 字符")
                logger.debug(f"   内容预览: {kb_info_raw[:200]}...")
                # 在知识库信息后附加检索统计
                kb_info_with_stats = f"{kb_info_raw}\n\n[检索统计: 数据库总数={kb_stats.get('total_in_db', 0)}, 检索={kb_stats.get('fetched', 0)}条, 通过={kb_stats.get('passed', 0)}条, 过滤={kb_stats.get('filtered', 0)}条, 阈值={kb_stats.get('threshold', 0)}]"
            else:
                # 即使没有命中，也显示检索统计
                logger.info(f"📚 [知识库] 未命中")
                if 'skipped' in kb_stats:
                    kb_info_with_stats = f"（无相关知识）\n[检索统计: 跳过原因={kb_stats.get('skipped')}]"
                elif 'error' in kb_stats:
                    kb_info_with_stats = f"（无相关知识）\n[检索统计: 错误={kb_stats.get('error')}]"
                else:
                    kb_info_with_stats = f"（无相关知识）\n[检索统计: 数据库总数={kb_stats.get('total_in_db', 0)}, 检索={kb_stats.get('fetched', 0)}条, 通过={kb_stats.get('passed', 0)}条, 过滤={kb_stats.get('filtered', 0)}条, 阈值={kb_stats.get('threshold', 0)}]"
            
            # 检索长期记忆（FAISS 向量检索）
            long_mem = ""
            faiss_mem = ""
            if user_id:
                # 传递 group_id 以支持场景隔离
                faiss_mem = vector_service.search_memory(
                    user_id, 
                    user_message,
                    group_id=group_id  # 传递群ID
                )
                if faiss_mem and faiss_mem != "（暂无相关长期记忆）":
                    logger.info(f"🧠 [FAISS向量] 命中 {len(faiss_mem)} 字符")
                    logger.debug(f"   内容预览: {faiss_mem[:200]}...")
                    long_mem = faiss_mem
            
            # === 检索关系图谱（RAG 知识图谱）===
            graph_mem = ""
            if user_id:
                try:
                    from src.core.RAGM import get_graph_retriever
                    graph_retriever = get_graph_retriever()
                    graph_mem = await graph_retriever.retrieve_with_graph(
                        user_id, user_message, user_name
                    )
                    if graph_mem:
                        logger.info(f"🕸️ [RAG图谱] 命中 {len(graph_mem)} 字符")
                        logger.debug(f"   内容预览: {graph_mem[:200]}...")
                except Exception as e:
                    logger.warning(f"⚠️ RAG图谱检索失败: {e}")
            
            # 合并两种记忆源
            if graph_mem:
                if long_mem:
                    # 将图谱记忆作为补充信息添加
                    long_mem = f"{long_mem}\n\n【相关事实】{graph_mem}"
                    logger.info(f"✅ [记忆合并] FAISS({len(faiss_mem)}字) + RAG图谱({len(graph_mem)}字) = 总计{len(long_mem)}字")
                else:
                    # 只有图谱记忆
                    long_mem = f"【相关事实】{graph_mem}"
                    logger.info(f"✅ [记忆来源] 仅RAG图谱 {len(graph_mem)}字")
            elif long_mem:
                logger.info(f"✅ [记忆来源] 仅FAISS向量 {len(long_mem)}字")
            
            # === 获取好感度温度 ===
            temperature = None
            if user_id:
                from src.core.Affection import get_affection_service
                affection_service = get_affection_service()
                default_temp = self.config.generator.temperature
                temperature = affection_service.get_temperature_for_user(user_id, default_temp)
                if temperature != default_temp:
                    logger.debug(f"💕 好感度温度调整: {default_temp} -> {temperature}")
            
            # === 获取最近对话（从短期内存） ===
            # === 获取最近对话（从短期内存） ===
            # 群聊用 group_id 作为 key，私聊用 user_id
            memory_key = group_id if group_id else user_id
            is_group = bool(group_id)
            
            # 从配置读取对话轮数
            role_config = ConfigManager.get_role_config()
            dialogue_config = getattr(role_config, 'recent_dialogue', None)
            if dialogue_config:
                max_rounds = dialogue_config.group_max_rounds if is_group else dialogue_config.private_max_rounds
                max_chars = dialogue_config.max_chars
                logger.debug(f"📝 对话配置: max_rounds={max_rounds}, max_chars={max_chars}, is_group={is_group}")
            else:
                max_rounds = 4 if is_group else 6
                max_chars = 400
                logger.debug(f"📝 使用默认对话配置: max_rounds={max_rounds}, max_chars={max_chars}")
            
            recent_dialogue = self._get_recent_dialogue(memory_key, user_name, max_rounds=max_rounds, max_chars=max_chars, is_group=is_group)
            
            # Stage 1: Organize context (产出记忆摘要，≤100字)
            # 群聊和私聊都需要场景分析，但群聊时长期记忆为空
            logger.info(f"🔍 Stage 1/3: Organizing context (memory summary)")
            context_summary = await self._organize_context(user_message, user_name, long_mem)
            logger.debug(f"   Memory summary: {context_summary[:100]}...")
            
            # === Stage 1.5: 整理知识库摘要（新增）===
            kb_summary = ""
            if kb_info_raw:
                logger.info(f"📚 Stage 1.5/3: Organizing knowledge base")
                logger.debug(f"   原始知识库内容: {kb_info_raw[:200]}...")
                # 传入原始内容（不含检索统计）给 LLM 整理
                kb_summary = await self._organize_knowledge(user_message, kb_info_raw)
                logger.info(f"   整理后摘要: {kb_summary[:100]}...")
                # 在整理后的摘要后附加检索统计
                kb_summary_with_stats = f"{kb_summary}\n\n[检索统计: 数据库总数={kb_stats.get('total_in_db', 0)}, 检索={kb_stats.get('fetched', 0)}条, 通过={kb_stats.get('passed', 0)}条, 过滤={kb_stats.get('filtered', 0)}条, 阈值={kb_stats.get('threshold', 0)}]"
            else:
                logger.info(f"📚 Stage 1.5/3: 跳过（无知识库内容）")
                kb_summary_with_stats = kb_info_with_stats
            
            # Stage 2: Generate reply (新版结构化 prompt)
            logger.info(f"✨ Stage 2/3: Generating reply (structured prompt)")
            final_reply = await self._generate_reply(
                context_summary, user_message, user_name, kb_summary_with_stats, 
                temperature_override=temperature,
                recent_dialogue=recent_dialogue,
                group_id=group_id,
                group_name=group_name,
                user_id=user_id
            )
            logger.debug(f"   Final reply: {final_reply[:100]}...")
            
            # === 回复守门员：检查是否跑偏 ===
            from src.core.persona_guard import check_reply_rules, check_reply_persona_match
            
            # 1. 规则检查（黑名单关键词）
            rules_ok, violation = check_reply_rules(final_reply)
            
            # 2. 人设向量相似度检查（可选，较耗时）
            # persona_ok, similarity = await check_reply_persona_match(final_reply, threshold=0.45)
            
            # 如果违规，触发纠偏重写
            if not rules_ok:
                logger.warning(f"🔄 触发纠偏重写: {violation}")
                final_reply = await self._correction_rewrite(
                    context_summary, user_message, user_name
                )
            
            # === 存储对话到短期内存（实时生效）===
            # 群聊用 group_id 作为 key，私聊用 user_id
            memory_key = group_id if group_id else user_id
            if memory_key:
                self._add_to_short_term_memory(memory_key, user_message, final_reply, sender_name=user_name)
            
            # === 存储对话到长期记忆（向量数据库，异步）===
            if user_id:
                # 传递 group_id 以支持双数据库存储
                vector_service.add_pair_memory(
                    user_id, 
                    user_message, 
                    final_reply,
                    group_id=group_id,  # 传递群ID
                    sender_name=user_name
                )
            
            # === 构建知识图谱（新增，异步后台任务）===
            if user_id:
                try:
                    from src.core.RAGM import get_graph_retriever
                    graph_retriever = get_graph_retriever()
                    # 后台任务，不阻塞响应
                    asyncio.create_task(
                        graph_retriever.add_dialogue_to_graph(
                            user_id, user_message, final_reply, user_name
                        )
                    )
                except Exception as e:
                    logger.warning(f"⚠️ 图谱构建任务创建失败: {e}")
            
            # === 更新好感度 ===
            if user_id:
                from src.core.Affection import get_affection_service
                affection_service = get_affection_service()
                await affection_service.update_affection(user_id, user_message, final_reply)
            
            return final_reply
            
        except Exception as e:
            logger.error(f"❌ Chat processing failed: {e}", exc_info=True)
            # 记录详细的错误上下文
            logger.error(f"   用户: {user_id}, 消息: {user_message[:100]}")
            error_reply = self.config.fallback.error_reply if self.config else "An error occurred. Please try again."
            return error_reply
    
    async def _organize_context(
        self,
        user_message: str,
        user_name: str = "用户",
        long_mem: str = ""
    ) -> str:
        """
        Stage 1: 生成记忆摘要（≤100字）
        
        职责：
        - 基于长期记忆，概括月代雪与用户之间的重要互动和关系特征
        - 输出一段话，不超过100字
        - 使用用户名或"对方"指代，禁止使用"用户"一词
        
        注意：知识库信息和最近对话会在 Stage 2 直接传递给推理模型
        
        Args:
            user_message: Current user message
            user_name: Name of the user
            long_mem: 长期记忆检索结果
            
        Returns:
            记忆摘要（≤100字）
        """
        if not self.config:
            self._refresh_config()
        
        organizer = self.config.organizer
        
        if not organizer.enabled:
            logger.warning("Organizer model disabled, skipping stage 1")
            return f"用户输入：{user_message}"
        
        # === 构建 Organizer 提示词 ===
        system_prompt = self._build_organizer_prompt()
        
        # 如果有长期记忆，将其作为系统提示词的一部分
        if long_mem and long_mem != "（暂无相关长期记忆）":
            # 格式化记忆内容，将 "User问" 替换为用户名，移除 [Pair] 标记
            formatted_mem = (
                long_mem
                .replace("[Pair] User问:", f"{user_name}:")
                .replace("User问:", f"{user_name}:")
                .replace("Bot答:", "月代雪:")
                .replace("[Pair] ", "")
            )
            
            # 使用占位符替换记忆内容
            memory_system_prompt = system_prompt.replace("{memory_content}", formatted_mem)
            
            user_prompt = (
                f"对话对象: {user_name}\n"
                f"当前消息: {user_message}\n\n"
                f"请整理上述历史记忆。"
            )
        else:
            # 无记忆时的简化处理，替换占位符为提示文本
            memory_system_prompt = system_prompt.replace(
                "{memory_content}", 
                "(暂无历史记忆)"
            )
            user_prompt = (
                f"对话对象: {user_name}\n"
                f"当前消息: {user_message}\n\n"
                f"这是首次对话，请输出: 首次对话，暂无历史互动"
            )
        
        messages = [
            ChatMessage(
                role="system",
                content=memory_system_prompt
            ),
            ChatMessage(
                role="user",
                content=user_prompt
            )
        ]
        
        try:
            start_time = time.time()
            response = await self._call_organizer_model(messages, organizer)
            summary = AsyncHTTPClient.parse_completion_response(response)
            elapsed_time = time.time() - start_time
            
            # 记录模型调用
            if summary:
                model_logger = get_model_logger()
                model_logger.log_organizer_call(
                    user_message=user_message,
                    context_summary=summary,
                    system_prompt=memory_system_prompt,
                    model_name=organizer.model_name,
                    temperature=organizer.temperature,
                    max_tokens=organizer.max_tokens,
                    elapsed_time=elapsed_time
                )
            
            return summary if summary else f"User input: {user_message}"
            
        except Exception as e:
            logger.error(f"❌ Context organization failed: {e}", exc_info=True)
            logger.error(f"   用户消息: {user_message[:100]}")
            if self.config.fallback.skip_organizer_on_failure:
                logger.warning("   Skipping organizer, proceeding to reply generation")
                return f"User input: {user_message}"
            else:
                raise
    
    async def _organize_knowledge(
        self,
        user_message: str,
        kb_info: str
    ) -> str:
        """
        Stage 1.5: 整理知识库摘要
        
        职责：
        - 从检索到的知识库中提取与当前对话相关的信息
        - 客观、简洁地整理成摘要
        - 输出不超过150字
        
        Args:
            user_message: 用户消息
            kb_info: 检索到的知识库信息
            
        Returns:
            知识库摘要（≤150字）
        """
        if not self.config:
            self._refresh_config()
        
        # 获取知识库整理器配置
        kb_organizer = getattr(self.config, 'kb_organizer', None)
        
        # 调试日志
        logger.debug(f"kb_organizer 配置: {kb_organizer}")
        if kb_organizer:
            logger.debug(f"kb_organizer.enabled: {getattr(kb_organizer, 'enabled', None)}")
        
        # 如果没有配置或未启用，直接返回原始内容
        if not kb_organizer:
            logger.warning("⚠️ kb_organizer 配置不存在，使用原始知识库内容")
            return kb_info
        
        if not getattr(kb_organizer, 'enabled', True):
            logger.warning("⚠️ kb_organizer 未启用，使用原始知识库内容")
            return kb_info
        
        # 获取模型配置（如果为空则使用 organizer 的配置）
        provider_name = getattr(kb_organizer, 'provider', '') or getattr(self.config.organizer, 'provider', '')
        model_name = getattr(kb_organizer, 'model_name', '') or self.config.organizer.model_name
        temperature = getattr(kb_organizer, 'temperature', 0.2)
        max_tokens = getattr(kb_organizer, 'max_tokens', 300)
        timeout = getattr(kb_organizer, 'timeout', 60)
        
        # 获取系统提示词
        system_prompt = getattr(kb_organizer, 'system_prompt', None)
        if not system_prompt:
            system_prompt = """你是知识库整理助手。从检索到的知识库中提取与用户消息相关的信息。

【输出要求】
1. 只输出与用户消息直接相关的信息
2. 客观、简洁、清晰，不超过150字
3. 如果知识库内容与用户消息无关，输出"无相关知识"
4. 不要编造信息，只基于提供的知识库内容"""
        
        user_prompt = f"""用户消息：{user_message}

知识库内容：
{kb_info}

请整理出与用户消息相关的知识（≤150字）："""
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt)
        ]
        
        try:
            start_time = time.time()
            
            # 获取供应商配置
            if not provider_name:
                provider_name = self.config.common.default_provider
            
            providers = getattr(self.config, 'providers', {})
            if provider_name in providers:
                provider = providers[provider_name]
                api_base = provider.api_base
                api_key = provider.api_key
                provider_timeout = provider.timeout
            else:
                raise ValueError(f"未找到供应商配置: {provider_name}")
            
            # 调用模型
            async with AsyncHTTPClient(timeout=timeout or provider_timeout) as client:
                response = await client.chat_completion(
                    api_base=api_base,
                    api_key=api_key,
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout or provider_timeout
                )
            
            summary = AsyncHTTPClient.parse_completion_response(response)
            elapsed_time = time.time() - start_time
            
            logger.info(f"📚 知识库整理完成: {len(summary)}字, 耗时{elapsed_time:.2f}s")
            logger.debug(f"   整理结果: {summary[:100]}...")
            
            return summary if summary else kb_info
            
        except Exception as e:
            logger.error(f"❌ 知识库整理失败: {e}")
            return kb_info
    
    async def _generate_reply(
        self,
        context_summary: str,
        user_message: str,
        user_name: str = "用户",
        kb_info: str = "",
        temperature_override: float = None,
        recent_dialogue: str = "",
        group_id: str = None,
        group_name: str = None,
        user_id: str = None
    ) -> str:
        """
        Stage 2: Reply generation (知识库在这里直接传递)
        
        Based on context summary, knowledge base, and persona, generate the final reply.
        
        Args:
            context_summary: Context from stage 1 (记忆摘要，≤100字)
            user_message: Original user message
            user_name: Name of the user
            kb_info: 知识库检索结果（已压缩为要点句）
            temperature_override: 温度覆盖值（来自好感度系统）
            recent_dialogue: 最近对话记录
            group_id: 群号（群聊时传入）
            group_name: 群名（群聊时传入）
            user_id: 用户ID（用于获取好感度）
            
        Returns:
            AI reply
        """
        if not self.config:
            self._refresh_config()
        
        generator = self.config.generator
        
        if not generator.enabled:
            logger.error("Generator model disabled")
            raise RuntimeError("Generator model not enabled")
        
        # 构建系统提示词（区分私聊/群聊模板）
        system_prompt = self._build_system_prompt(
            context_summary, user_name, kb_info, recent_dialogue,
            group_id=group_id, group_name=group_name, user_id=user_id
        )
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message)
        ]
        
        # 使用好感度温度或默认温度
        actual_temperature = temperature_override if temperature_override is not None else generator.temperature
        
        try:
            start_time = time.time()
            response = await self._call_generator_model(messages, generator, actual_temperature)
            reply = AsyncHTTPClient.parse_completion_response(response)
            reasoning = AsyncHTTPClient.parse_reasoning_content(response)  # 提取思考过程
            elapsed_time = time.time() - start_time
            
            # === 后处理：强制移除括号内容（兜底） ===
            if reply:
                import re
                # 移除所有括号及其内容（包括中英文括号）
                reply = re.sub(r'[（(].*?[）)]', '', reply)
                reply = re.sub(r'[【\[].*?[】\]]', '', reply)
                reply = re.sub(r'[《<].*?[》>]', '', reply)
                # 移除所有句号
                reply = reply.replace('。', '')
                # 清理多余空格
                reply = re.sub(r'\s+', ' ', reply).strip()
                # 如果过滤后为空，用省略号兜底
                if not reply or len(reply) < 2:
                    reply = "......"
            
            # 记录模型调用（包含思考过程）
            if reply:
                model_logger = get_model_logger()
                model_logger.log_generator_call(
                    user_message=user_message,
                    context_summary=context_summary,
                    system_prompt=system_prompt,
                    reply=reply,
                    model_name=generator.model_name,
                    temperature=actual_temperature,
                    max_tokens=generator.max_tokens,
                    elapsed_time=elapsed_time,
                    reasoning_content=reasoning  # 传递思考过程
                )
            
            return reply if reply else self.config.fallback.error_reply
            
        except Exception as e:
            logger.error(f"Reply generation failed: {e}", exc_info=True)
            logger.error(f"   用户消息: {user_message[:100]}")
            logger.error(f"   上下文摘要: {context_summary[:100]}")
            raise
    
    def _format_chat_history(self, history: List[ChatMessage]) -> str:
        """Format chat history for readability"""
        if not history:
            return "(No chat history)"
        
        lines = []
        for msg in history:
            if msg.role == "user":
                lines.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                lines.append(f"Yuki: {msg.content}")
        
        return "\n".join(lines[-10:])
    
    def _get_recent_dialogue(
        self, 
        memory_key: str, 
        user_name: str, 
        max_rounds: int = 6,
        max_chars: int = 400,
        is_group: bool = False
    ) -> str:
        """
        获取最近对话记录（从短期内存）
        
        私聊格式：
        {user_name}：……
        月代雪：……
        
        群聊格式：
        {sender_name}：……
        月代雪：……
        
        Args:
            memory_key: 内存 key（私聊用 user_id，群聊用 group_id）
            user_name: 当前用户昵称（私聊时使用）
            max_rounds: 最大轮数
            max_chars: 最大字符数
            is_group: 是否群聊
            
        Returns:
            格式化的对话字符串
        """
        try:
            # 从短期内存获取
            if memory_key not in self._short_term_memory:
                return ""
            
            pairs = list(self._short_term_memory[memory_key])
            if not pairs:
                return ""
            
            # 格式化输出，优先保证轮数
            lines = []
            role_name = ConfigManager.get_role_config().persona.name
            
            # 从旧到新遍历，取最近 max_rounds 轮
            for item in pairs[-max_rounds:]:
                # 兼容旧格式 (query, reply) 和新格式 (query, reply, sender_name)
                if len(item) == 3:
                    query, reply, sender_name = item
                else:
                    query, reply = item
                    sender_name = user_name  # 私聊或旧数据用当前用户名
                
                # 群聊显示发送者名字，私聊统一用 user_name
                display_name = sender_name if is_group else user_name
                line = f"{display_name}：{query}\n{role_name}：{reply}"
                lines.append(line)
            
            # 拼接所有对话
            result = "\n".join(lines)
            
            # 如果超过字符限制，从前面截断（保留最近的对话）
            if len(result) > max_chars:
                # 从后往前累加，保证最近的对话不被截断
                truncated_lines = []
                total_chars = 0
                for line in reversed(lines):
                    if total_chars + len(line) + 1 > max_chars:  # +1 for newline
                        break
                    truncated_lines.insert(0, line)
                    total_chars += len(line) + 1
                result = "\n".join(truncated_lines)
                logger.debug(f"对话记录超长，截断为 {len(truncated_lines)} 轮（{total_chars}字）")
            
            return result
            
        except Exception as e:
            logger.warning(f"获取最近对话失败: {e}")
            return ""
    
    def _add_to_short_term_memory(self, memory_key: str, query: str, reply: str, sender_name: str = None) -> None:
        """
        添加对话到短期内存
        
        Args:
            memory_key: 内存 key（私聊用 user_id，群聊用 group_id）
            query: 用户消息
            reply: Bot 回复
            sender_name: 发送者昵称（群聊时使用）
        """
        if memory_key not in self._short_term_memory:
            self._short_term_memory[memory_key] = deque(maxlen=self._max_short_term_rounds)
        
        # 存储格式：(query, reply, sender_name)
        self._short_term_memory[memory_key].append((query, reply, sender_name or "用户"))
    
    def _compress_kb_info(self, kb_info: str, max_items: int = 3) -> str:
        """
        压缩知识库信息为要点句
        
        将检索到的原文压缩成每条 50-80 字的要点句，保留完整语义
        
        Args:
            kb_info: 原始知识库检索结果
            max_items: 最大条目数
            
        Returns:
            压缩后的知识库信息（编号列表）
        """
        if not kb_info or kb_info == "（无相关知识）":
            return "（无相关知识）"
        
        try:
            # 解析检索结果（按条目分割）
            lines = kb_info.strip().split('\n')
            compressed_items = []
            current_item = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 检测新条目开始（以数字+点开头）
                if line and line[0].isdigit() and '.' in line[:3]:
                    if current_item:
                        # 处理上一条
                        item_text = ' '.join(current_item)
                        compressed = self._extract_key_sentence(item_text)
                        if compressed:
                            compressed_items.append(compressed)
                    current_item = [line]
                else:
                    current_item.append(line)
            
            # 处理最后一条
            if current_item:
                item_text = ' '.join(current_item)
                compressed = self._extract_key_sentence(item_text)
                if compressed:
                    compressed_items.append(compressed)
            
            # 如果解析失败，直接返回原文（不截断）
            if not compressed_items:
                return kb_info
            
            # 格式化输出（重新编号，避免重复）
            result_lines = []
            for i, item in enumerate(compressed_items[:max_items], 1):
                result_lines.append(f"{i}. {item}")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            logger.warning(f"压缩知识库信息失败: {e}")
            return kb_info
    
    def _extract_key_sentence(self, text: str, max_len: int = 80) -> str:
        """
        从文本中提取关键句（50-80字），保留完整语义
        
        策略：移除格式标记和原有编号，取完整的前1-2句
        """
        if not text:
            return ""
        
        import re
        
        # 移除格式标记
        text = text.replace("标题：", "").replace("内容：", "").replace("相关性：", "")
        text = text.replace("搜索类型：vector", "").replace("搜索类型：keyword", "")
        
        # 移除开头的编号（如 "1. " "1。" "2. " 等）
        text = re.sub(r'^[\d]+[.。]\s*', '', text.strip())
        
        # 移除来源标记（如 "魔女审判知识库：" "魔裁设定："）
        text = re.sub(r'^[^：:]+[：:]\s*', '', text, count=1)
        
        # 按句号分割，保留完整句子
        sentences = []
        # 用正则分割，保留分隔符
        parts = re.split(r'([。！？])', text)
        
        # 重组句子（内容+标点）
        i = 0
        while i < len(parts):
            sentence = parts[i].strip()
            if i + 1 < len(parts) and parts[i + 1] in '。！？':
                sentence += parts[i + 1]
                i += 2
            else:
                i += 1
            if sentence:
                sentences.append(sentence)
        
        if not sentences:
            # 没有句号，直接用原文
            result = text.strip()
        else:
            # 取第一句
            result = sentences[0]
            
            # 如果太短（<30字）且有第二句，拼接
            if len(result) < 30 and len(sentences) > 1:
                result = result + sentences[1]
        
        # 如果超长，在句号处截断（而不是硬截断）
        if len(result) > max_len:
            # 找最后一个句号位置
            for sep in ['。', '！', '？', '，']:
                last_sep = result[:max_len].rfind(sep)
                if last_sep > 30:  # 至少保留30字
                    result = result[:last_sep + 1]
                    break
            else:
                # 实在找不到，硬截断但不加省略号（避免信息丢失感）
                result = result[:max_len]
        
        return result
        
        return result
    
    def _build_organizer_prompt(self) -> str:
        """Build organizer model system prompt - no user info needed in this stage"""
        organizer_config = self.config.organizer
        
        # 构建提示词（此阶段不需要填充用户名和时间）
        prompt_template = organizer_config.system_prompt
        
        if not prompt_template:
            # 如果没有配置，使用默认提示词
            return "分析用户消息，提取意图、主题、关键信息和应对态度。不要生成回复。"
        
        return prompt_template
    

    
    def _build_system_prompt(
        self, 
        context_summary: str, 
        user_name: str = "用户",
        kb_info: str = "",
        recent_dialogue: str = "",
        group_id: str = None,
        group_name: str = None,
        user_id: str = None
    ) -> str:
        """
        Build complete system prompt - 区分私聊/群聊模板
        
        Args:
            context_summary: Organizer 产出的记忆摘要（≤100字）
            user_name: 用户名
            kb_info: 知识库检索结果（已压缩为要点句）
            recent_dialogue: 最近对话记录
            group_id: 群号（群聊时传入）
            group_name: 群名（群聊时传入）
            user_id: 用户ID（用于获取好感度）
        """
        from datetime import datetime
        
        role_config = ConfigManager.get_role_config()
        
        # 根据是否群聊选择模板
        is_group = bool(group_id)
        if is_group:
            template = getattr(role_config.system_prompt_template, 'group_template', None)
            if not template:
                # 如果没有群聊模板，用私聊模板
                template = role_config.system_prompt_template.template
        else:
            template = role_config.system_prompt_template.template
        
        # 角色核心设定（写死在配置里）
        role_profile = getattr(role_config.system_prompt_template, 'role_profile', '') or role_config.expression.description
        
        # 语言风格
        expression_style = role_config.expression.speaking_style or "理性、冷漠，说话平淡克制"
        
        # 规则（支持 {user_name} 占位符）
        conversation_rules = role_config.system_prompt_template.conversation_rules
        if conversation_rules:
            conversation_rules = conversation_rules.replace("{user_name}", user_name)
        
        # 当前时间
        current_datetime = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        
        # 记忆摘要（来自 context_summary，如果为空则显示默认）
        memory_summary = context_summary.strip() if context_summary else "暂无长期记忆"
        
        # 最近对话（如果为空则显示默认）
        if not recent_dialogue:
            recent_dialogue = "（暂无最近对话）"
        
        # 知识库信息（如果为空则显示默认）
        if not kb_info:
            kb_info = "（无相关知识）"
        
        # 群名（如果为空则用群号）
        display_group_name = group_name or group_id or ""
        
        # 获取好感度信息（私聊和群聊都获取个人好感度）
        affection_level = "未知"
        if user_id:
            try:
                from src.core.Affection import get_affection_service
                affection_service = get_affection_service()
                info = affection_service.get_affection_info_for_display(user_id)
                affection_level = f"{info['level_name']}（{info['score']}/10）"
            except Exception:
                affection_level = "未知"
        
        # 填充模板（兼容私聊和群聊）
        try:
            system_prompt = template.format(
                role_profile=role_profile,
                expression_style=expression_style,
                current_datetime=current_datetime,
                user_name=user_name,
                memory_summary=memory_summary,
                recent_dialogue=recent_dialogue,
                kb_info=kb_info,
                conversation_rules=conversation_rules,
                group_name=display_group_name,  # 群聊模板用
                affection_level=affection_level  # 好感度
            )
        except KeyError:
            # 如果模板缺少某些占位符，用私聊模板兜底
            system_prompt = role_config.system_prompt_template.template.format(
                role_profile=role_profile,
                expression_style=expression_style,
                current_datetime=current_datetime,
                user_name=user_name,
                memory_summary=memory_summary,
                recent_dialogue=recent_dialogue,
                kb_info=kb_info,
                conversation_rules=conversation_rules,
                affection_level=affection_level
            )
        
        return system_prompt
    
    def _get_provider_config(self, provider_name: str = None):
        """
        获取供应商配置
        
        Args:
            provider_name: 供应商名称，为空则用默认供应商
            
        Returns:
            (api_base, api_key, timeout)
        """
        # 确定使用哪个供应商
        if not provider_name:
            provider_name = self.config.common.default_provider
        
        # 从 providers 字典获取
        providers = getattr(self.config, 'providers', {})
        if provider_name in providers:
            provider = providers[provider_name]
            return provider.api_base, provider.api_key, provider.timeout
        
        # 兼容旧配置：如果没有 providers，用 common 里的
        if hasattr(self.config.common, 'api_base') and self.config.common.api_base:
            return self.config.common.api_base, self.config.common.api_key, self.config.common.timeout
        
        raise ValueError(f"未找到供应商配置: {provider_name}")
    
    async def _call_organizer_model(
        self,
        messages: List[ChatMessage],
        organizer_config
    ) -> Dict[str, Any]:
        """Call organizer model"""
        # 获取供应商配置
        provider_name = getattr(organizer_config, 'provider', '') or None
        api_base, api_key, provider_timeout = self._get_provider_config(provider_name)
        timeout = organizer_config.timeout or provider_timeout
        
        async with AsyncHTTPClient(timeout=timeout) as client:
            response = await client.chat_completion(
                api_base=api_base,
                api_key=api_key,
                model=organizer_config.model_name,
                messages=messages,
                temperature=organizer_config.temperature,
                max_tokens=organizer_config.max_tokens,
                timeout=timeout
            )
            
            # 记录 LLM 使用统计
            self._record_llm_stats(organizer_config.model_name, response)
            
            return response
    
    async def _call_generator_model(
        self,
        messages: List[ChatMessage],
        generator_config,
        temperature: float = None
    ) -> Dict[str, Any]:
        """Call generator model"""
        # 获取供应商配置
        provider_name = getattr(generator_config, 'provider', '') or None
        api_base, api_key, provider_timeout = self._get_provider_config(provider_name)
        timeout = generator_config.timeout or provider_timeout
        
        # 使用传入的温度或配置的默认温度
        actual_temp = temperature if temperature is not None else generator_config.temperature
        
        async with AsyncHTTPClient(timeout=timeout) as client:
            response = await client.chat_completion(
                api_base=api_base,
                api_key=api_key,
                model=generator_config.model_name,
                messages=messages,
                temperature=actual_temp,
                max_tokens=generator_config.max_tokens,
                timeout=timeout
            )
            
            # 记录 LLM 使用统计
            self._record_llm_stats(generator_config.model_name, response)
            
            return response
    
    def _record_llm_stats(self, model_name: str, response: Dict[str, Any]) -> None:
        """记录 LLM 使用统计"""
        try:
            from src.services.stats_service import get_stats_service
            usage = AsyncHTTPClient.parse_usage(response)
            
            if usage["prompt_tokens"] > 0 or usage["completion_tokens"] > 0:
                stats_service = get_stats_service()
                stats_service.record_llm_usage(
                    model_name=model_name,
                    input_tokens=usage["prompt_tokens"],
                    output_tokens=usage["completion_tokens"]
                )
        except Exception as e:
            logger.warning(f"记录 LLM 统计失败: {e}")
    
    async def _correction_rewrite(
        self,
        context_summary: str,
        user_message: str,
        user_name: str
    ) -> str:
        """
        纠偏重写：当回复跑偏时，用精简 prompt 重新生成
        
        只传最核心的人设锚点，不传知识库等附加信息
        """
        if not self.config:
            self._refresh_config()
        
        generator = self.config.generator
        role_config = ConfigManager.get_role_config()
        
        # 精简的纠偏 prompt
        correction_prompt = f"""你是月代雪，魔女种族最后的幸存者。说话冷淡简短，1-2句话。

上一次回复不符合角色设定。请重新回复下面的用户消息，严格保持角色。
禁止说"作为AI"或讨论规则本身。

场景概括：{context_summary[:200]}
用户（{user_name}）说：{user_message}"""
        
        messages = [
            ChatMessage(role="user", content=correction_prompt)
        ]
        
        try:
            response = await self._call_generator_model(
                messages, generator, temperature=0.5  # 降低温度增加稳定性
            )
            reply = AsyncHTTPClient.parse_completion_response(response)
            logger.info(f"🔄 纠偏重写完成: {reply[:50]}...")
            return reply if reply else self.config.fallback.error_reply
        except Exception as e:
            logger.error(f"❌ 纠偏重写失败: {e}")
            return "......"  # 最简兜底


_ai_manager: Optional[AIManager] = None


def get_ai_manager() -> AIManager:
    """Get global AI Manager singleton"""
    global _ai_manager
    if _ai_manager is None:
        _ai_manager = AIManager()
    return _ai_manager
