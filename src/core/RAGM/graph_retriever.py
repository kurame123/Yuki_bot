"""
图谱检索器
基于知识图谱增强记忆检索
"""
import json
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from src.core.logger import logger
from src.core.RAGM.graph_storage import get_graph_storage
from src.core.RAGM.entity_extractor import get_entity_extractor


class GraphRetriever:
    """图谱增强检索器"""
    
    def __init__(self):
        self.storage = get_graph_storage()
        self.extractor = get_entity_extractor()
        logger.info("✅ 图谱检索器初始化")
    
    async def retrieve_with_graph(
        self,
        user_id: str,
        query: str,
        user_name: str = "用户",
        max_results: int = 5
    ) -> str:
        """
        基于图谱的增强检索(增强版: 支持时间查询和指代消歧)
        
        流程:
        1. 从查询中提取关键实体和时间指代(使用 LLM)
        2. 在图谱中查找相关实体(支持别名匹配)
        3. 如果有时间指代，优先返回最近的关系
        4. 遍历图谱获取关联信息
        5. 格式化返回
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            user_name: 用户名
            max_results: 最大返回条数
            
        Returns:
            格式化的图谱记忆文本
        """
        logger.debug(f"🔍 [图谱检索] user={user_id}, query={query[:50]}")
        
        # 1. 提取查询中的关键实体和时间指代
        keywords, time_ref = await self._extract_keywords_with_time(query, user_name)
        
        # 如果 LLM 提取失败，回退到简单提取
        if not keywords:
            keywords = self._extract_keywords_simple(query)
            time_ref = self._extract_time_simple(query)
        
        logger.info(f"🔍 [图谱检索] 提取关键词: {keywords}, 时间指代: {time_ref or '无'}")
        
        if not keywords:
            logger.debug(f"   无关键词，跳过检索")
            return ""
        
        # 2. 在图谱中搜索相关实体（支持别名匹配）
        all_entities = []
        for keyword in keywords[:3]:  # 最多3个关键词
            # 直接搜索实体名
            entities = self.storage.search_entities(user_id, keyword, limit=3)
            
            # 搜索别名（通过 properties.aliases）
            alias_entities = self._search_by_alias(user_id, keyword)
            
            combined = entities + alias_entities
            
            if combined:
                logger.info(f"   关键词 '{keyword}' 找到 {len(combined)} 个实体:")
                for e in combined:
                    aliases = e.get('properties', {}).get('aliases', [])
                    alias_str = f" (别名: {', '.join(aliases)})" if aliases else ""
                    logger.info(f"     - {e['entity']} ({e['entity_type']}){alias_str}")
            
            all_entities.extend(combined)
        
        if not all_entities:
            logger.info(f"   未找到相关实体")
            return ""
        
        logger.info(f"   总计找到 {len(all_entities)} 个相关实体")
        
        # 3. 获取实体的邻居关系（1-2跳），如果有时间指代则优先最近的
        graph_info = []
        seen_relations = set()
        
        logger.info(f"   开始遍历图谱关系:")
        
        for entity_info in all_entities[:max_results]:
            entity = entity_info["entity"]
            
            # 获取邻居
            neighbors = self.storage.get_neighbors(user_id, entity, max_depth=2)
            
            # 如果有时间指代，按时间戳排序（最近的优先）
            if time_ref and neighbors:
                neighbors = self._filter_by_time(neighbors, time_ref)
                logger.info(f"     实体 '{entity}' 有 {len(neighbors)} 个邻居（时间过滤: {time_ref}）")
            elif neighbors:
                logger.info(f"     实体 '{entity}' 有 {len(neighbors)} 个邻居")
            
            for neighbor in neighbors[:5]:  # 每个实体最多5个邻居
                relation_key = f"{neighbor['source']}-{neighbor['relation']}-{neighbor['target']}"
                
                if relation_key not in seen_relations:
                    seen_relations.add(relation_key)
                    
                    # 格式化关系（自然语言描述，包含时间信息）
                    time_info = neighbor.get('properties', {}).get('time_ref', '')
                    if time_info:
                        relation_text = f"{time_info}{neighbor['source']}{neighbor['relation']}{neighbor['target']}"
                    else:
                        relation_text = f"{neighbor['source']}{neighbor['relation']}{neighbor['target']}"
                    
                    graph_info.append(relation_text)
                    logger.debug(f"       [{neighbor['depth']}跳] {relation_text}")
        
        if not graph_info:
            logger.info(f"   未找到有效关系")
            return ""
        
        # 4. 格式化输出（自然语言风格）
        result = "、".join(graph_info[:8])  # 最多8条，用顿号连接
        
        logger.info(f"🕸️ [图谱检索] 返回 {len(graph_info)} 条关系")
        
        return result
    
    async def _extract_keywords_with_time(self, query: str, user_name: str) -> Tuple[List[str], str]:
        """
        使用 LLM 提取关键实体和时间指代(增强版)
        
        Args:
            query: 查询文本
            user_name: 用户名
            
        Returns:
            (关键词列表, 时间指代)
        """
        try:
            from src.core.config_manager import ConfigManager
            from src.services.http_client import AsyncHTTPClient
            from src.models.api_types import ChatMessage
            
            ai_config = ConfigManager.get_ai_config()
            organizer = ai_config.organizer
            
            # 构建提示词
            system_prompt = f"""你是关键词提取助手。从用户消息中提取关键实体和时间指代。

【输出格式】
第一行: 2-3个关键词(用逗号分隔)
第二行: 时间指代(如"昨天"、"上次"、"最近"，没有则输出"无")

【示例1】
输入: 你怎么知道她不需要
输出:
她，不需要
无
"""
            
            user_prompt = f"用户（{user_name}）说：{query}\n\n请提取关键实体和时间指代："
            
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt)
            ]
            
            # 获取供应商配置
            provider_name = getattr(organizer, 'provider', '') or ai_config.common.default_provider
            providers = getattr(ai_config, 'providers', {})
            
            if provider_name in providers:
                provider = providers[provider_name]
                api_base = provider.api_base
                api_key = provider.api_key
                timeout = provider.timeout
            else:
                return [], ""
            
            async with AsyncHTTPClient(timeout=timeout) as client:
                response = await client.chat_completion(
                    api_base=api_base,
                    api_key=api_key,
                    model=organizer.model_name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=50,
                    timeout=timeout
                )
            
            result = AsyncHTTPClient.parse_completion_response(response)
            
            if result:
                # 解析两行输出
                lines = [line.strip() for line in result.strip().split('\n') if line.strip()]
                
                if len(lines) >= 1:
                    # 第一行：关键词
                    keywords = [k.strip() for k in lines[0].split(',') if k.strip()]
                    
                    # 第二行：时间指代
                    time_ref = ""
                    if len(lines) >= 2 and lines[1] != "无":
                        time_ref = lines[1]
                    
                    logger.debug(f"   LLM 提取: keywords={keywords}, time_ref={time_ref}")
                    return keywords[:5], time_ref
            
            return [], ""
        
        except Exception as e:
            logger.debug(f"   LLM 提取失败: {e}")
            return [], ""
    
    async def _extract_keywords_llm(self, query: str, user_name: str) -> List[str]:
        """
        使用 LLM 提取关键实体（更准确）
        
        Args:
            query: 查询文本
            user_name: 用户名
            
        Returns:
            关键词列表
        """
        try:
            from src.core.config_manager import ConfigManager
            from src.services.http_client import AsyncHTTPClient
            from src.models.api_types import ChatMessage
            
            ai_config = ConfigManager.get_ai_config()
            organizer = ai_config.organizer
            
            # 构建提示词
            system_prompt = f"""你是关键词提取助手。从用户消息中提取关键实体(人名、地名、物品、事件等)。

【输出格式】
只输出2-3个关键词，用逗号分隔，不要其他内容。

【示例】
输入: 你怎么知道她不需要
输出: 她，不需要
"""
            
            user_prompt = f"用户（{user_name}）说：{query}\n\n请提取关键实体："
            
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt)
            ]
            
            # 获取供应商配置
            provider_name = getattr(organizer, 'provider', '') or ai_config.common.default_provider
            providers = getattr(ai_config, 'providers', {})
            
            if provider_name in providers:
                provider = providers[provider_name]
                api_base = provider.api_base
                api_key = provider.api_key
                timeout = provider.timeout
            else:
                return []
            
            async with AsyncHTTPClient(timeout=timeout) as client:
                response = await client.chat_completion(
                    api_base=api_base,
                    api_key=api_key,
                    model=organizer.model_name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=50,
                    timeout=timeout
                )
            
            result = AsyncHTTPClient.parse_completion_response(response)
            
            if result:
                # 解析逗号分隔的关键词
                keywords = [k.strip() for k in result.split(',') if k.strip()]
                logger.debug(f"   LLM 提取: {keywords}")
                return keywords[:5]
            
            return []
        
        except Exception as e:
            logger.debug(f"   LLM 提取失败: {e}")
            return []
    
    def _extract_keywords_simple(self, text: str) -> List[str]:
        """
        智能关键词提取
        
        策略：
        1. 提取名词（人名、地名、物品等）
        2. 提取动词（动作、行为）
        3. 过滤停用词和无意义词
        """
        import re
        
        keywords = []
        
        # 1. 提取中文词（2-4字的连续中文）
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        
        # 2. 停用词过滤（扩展版）
        stopwords = {
            # 疑问词
            '什么', '怎么', '为什么', '哪里', '怎样', '如何', '是否', '可以', '能不能', '有没有',
            '为何', '何时', '何地', '谁的', '哪个', '哪些',
            # 代词
            '你的', '我的', '他的', '她的', '它的', '我们', '你们', '他们',
            '这个', '那个', '这些', '那些', '这样', '那样',
            # 动词
            '知道', '觉得', '认为', '感觉', '想要', '希望', '需要', '应该',
            # 其他
            '不是', '没有', '不要', '不会', '不能', '还是', '或者', '但是',
            '因为', '所以', '如果', '虽然', '然后', '接着', '于是'
        }
        
        # 3. 过滤并去重
        seen = set()
        for word in chinese_words:
            if word not in stopwords and word not in seen and len(word) >= 2:
                keywords.append(word)
                seen.add(word)
        
        # 4. 提取英文词（3字母以上）
        english_words = re.findall(r'[a-zA-Z]{3,}', text)
        for word in english_words:
            if word.lower() not in seen:
                keywords.append(word)
                seen.add(word.lower())
        
        # 5. 限制数量
        return keywords[:5]
    
    def _extract_time_simple(self, text: str) -> str:
        """
        简单提取时间指代
        
        Returns:
            时间指代词（如"昨天"、"上次"），没有则返回空字符串
        """
        time_keywords = [
            '昨天', '前天', '上次', '最近', '刚才', '刚刚', '之前', 
            '上周', '上个月', '去年', '那天', '那时', '当时'
        ]
        
        for keyword in time_keywords:
            if keyword in text:
                return keyword
        
        return ""
    
    def _search_by_alias(self, user_id: str, alias: str) -> List[Dict[str, Any]]:
        """
        通过别名搜索实体
        
        Args:
            user_id: 用户 ID
            alias: 别名(如"她"、"那个人")
            
        Returns:
            匹配的实体列表
        """
        conn = sqlite3.connect(str(self.storage.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT entity, entity_type, properties, updated_at
            FROM nodes
            WHERE user_id = ? AND properties LIKE ?
            ORDER BY updated_at DESC
            LIMIT 5
        """, (user_id, f'%"{alias}"%'))
        
        results = []
        for row in cursor.fetchall():
            entity, entity_type, props, updated_at = row
            props_dict = json.loads(props) if props else {}
            
            # 验证别名确实在列表中
            aliases = props_dict.get('aliases', [])
            if alias in aliases:
                results.append({
                    "entity": entity,
                    "entity_type": entity_type,
                    "properties": props_dict,
                    "updated_at": updated_at
                })
        
        conn.close()
        return results
    
    def _filter_by_time(self, neighbors: List[Dict[str, Any]], time_ref: str) -> List[Dict[str, Any]]:
        """
        根据时间指代过滤关系
        
        策略:
        - "上次"/"最近"/"刚才" -> 返回最近的关系(按时间戳排序)
        - "昨天"/"前天" -> 返回对应时间范围的关系
        - 其他 -> 不过滤
        
        Args:
            neighbors: 邻居关系列表
            time_ref: 时间指代
            
        Returns:
            过滤后的关系列表
        """
        import time as time_module
        
        current_time = int(time_module.time())
        
        # 定义时间范围（秒）
        time_ranges = {
            '刚才': 3600,           # 1小时内
            '刚刚': 3600,
            '最近': 86400 * 7,      # 7天内
            '昨天': (86400, 86400 * 2),  # 1-2天前
            '前天': (86400 * 2, 86400 * 3),  # 2-3天前
            '上次': 86400 * 30,     # 30天内
            '之前': 86400 * 30,
        }
        
        # 如果时间指代不在范围内，不过滤
        if time_ref not in time_ranges:
            return neighbors
        
        # 提取有时间戳的关系
        timed_neighbors = []
        for neighbor in neighbors:
            props = neighbor.get('properties', {})
            timestamp = props.get('timestamp')
            
            if timestamp:
                neighbor['_timestamp'] = timestamp
                timed_neighbors.append(neighbor)
        
        # 如果没有时间戳
        if not timed_neighbors:
            return neighbors
        
        # 根据时间指代过滤
        time_range = time_ranges[time_ref]
        
        if isinstance(time_range, tuple):
            # 范围过滤（如"昨天"）
            min_time, max_time = time_range
            filtered = [
                n for n in timed_neighbors
                if min_time <= (current_time - n['_timestamp']) < max_time
            ]
        else:
            # 单一范围过滤（如"最近"）
            filtered = [
                n for n in timed_neighbors
                if (current_time - n['_timestamp']) <= time_range
            ]
        
        # 如果过滤后为空，返回最近的几条
        if not filtered:
            timed_neighbors.sort(key=lambda x: x['_timestamp'], reverse=True)
            return timed_neighbors[:5]
        
        # 按时间排序（最近的优先）
        filtered.sort(key=lambda x: x['_timestamp'], reverse=True)
        
        return filtered
    
    async def add_dialogue_to_graph(
        self,
        user_id: str,
        user_message: str,
        bot_reply: str,
        user_name: str = "用户"
    ):
        """
        将对话添加到知识图谱(增强版: 支持时间和别名)
        
        Args:
            user_id: 用户 ID
            user_message: 用户消息
            bot_reply: Bot 回复
            user_name: 用户名
        """
        try:
            logger.info(f"📊 [图谱构建] 开始提取实体和关系")
            logger.debug(f"   用户消息: {user_message[:50]}")
            logger.debug(f"   Bot回复: {bot_reply[:50]}")
            
            # 提取实体和关系(增强版)
            extracted = await self.extractor.extract_from_dialogue(
                user_message, bot_reply, user_name
            )
            
            entities = extracted.get("entities", [])
            relations = extracted.get("relations", [])
            time_context = extracted.get("time_context", "")
            
            if not entities and not relations:
                logger.info(f"📊 [图谱构建] 无实体或关系，跳过")
                return
            
            # 添加实体到图谱（包含别名）
            logger.info(f"📊 [图谱构建] 添加 {len(entities)} 个实体:")
            for entity in entities:
                alias = entity.get("alias", "")
                self.storage.add_node(
                    user_id=user_id,
                    entity=entity["name"],
                    entity_type=entity.get("type", "其他"),
                    alias=alias if alias else None
                )
                
                alias_info = f" (别名: {alias})" if alias else ""
                logger.info(f"     + 实体: {entity['name']} ({entity.get('type', '其他')}){alias_info}")
            
            # 添加关系到图谱（包含时间指代）
            logger.info(f"📊 [图谱构建] 添加 {len(relations)} 个关系:")
            for relation in relations:
                time_ref = relation.get("time_ref", "") or time_context
                self.storage.add_edge(
                    user_id=user_id,
                    source=relation["source"],
                    target=relation["target"],
                    relation=relation["relation"],
                    time_ref=time_ref if time_ref else None
                )
                
                time_info = f" [{time_ref}]" if time_ref else ""
                logger.info(f"     + 关系: {relation['source']} → {relation['relation']} → {relation['target']}{time_info}")
            
            logger.info(f"✅ [图谱构建] 完成")
            
        except Exception as e:
            logger.warning(f"⚠️ 图谱构建失败: {e}", exc_info=True)


# 全局单例
_graph_retriever: Optional[GraphRetriever] = None


def get_graph_retriever() -> GraphRetriever:
    """获取全局图谱检索器单例"""
    global _graph_retriever
    if _graph_retriever is None:
        _graph_retriever = GraphRetriever()
    return _graph_retriever
