"""
Yuki 主聊天插件匹配器
处理来自 QQ 的聊天消息

v2.0 更新：
- 支持图片识别：用户发送的图片会被转换为文字描述，参与对话和记忆
- 图片描述格式：[图片描述：xxx]
"""
import nonebot
import asyncio
import random
from pathlib import Path
from typing import Tuple, List
from nonebot import on_command, on_message
from nonebot.rule import to_me, is_type, Rule
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.exception import FinishedException
from src.services.ai_manager import get_ai_manager
from src.services.emoji_service import get_emoji_service
from src.services.vision_caption_service import get_vision_caption_service
from src.services.injection_guard_service import get_injection_guard
from src.core.logger import logger
from src.core.config_manager import ConfigManager
from src.core.message_splitter import get_message_splitter
from src.core.security import whitelist_rule
from src.core.temp_blacklist import get_temp_blacklist


# ============ 辅助函数：异步加载历史消息（不阻塞） ============
async def load_history_async(bot: Bot, ai_manager, user_id: str, group_id: str = None):
    """
    异步加载历史消息到短期内存（后台任务，不阻塞主流程）
    
    Args:
        bot: NoneBot Bot 实例
        ai_manager: AI 管理器实例
        user_id: 用户 ID
        group_id: 群 ID（可选）
    """
    try:
        if group_id:
            await ai_manager.load_group_history_from_napcat(bot, group_id, user_id)
        else:
            await ai_manager.load_history_from_napcat(bot, user_id)
    except Exception as e:
        logger.debug(f"后台加载历史消息失败（可忽略）: {e}")


# ============ 防火墙规则：过滤命令 ============
async def is_not_command(event: MessageEvent) -> bool:
    """
    检查消息是否不是命令
    如果消息以 / 开头，返回 False（不处理）
    """
    text = event.get_plaintext().strip()
    return not text.startswith("/")


# 组合规则：必须在白名单内 AND 不是命令
chat_rule = whitelist_rule & Rule(is_not_command)


# 延迟初始化所有服务，确保在配置加载之后
_ai_manager_instance = None
_emoji_service_instance = None
_message_splitter_instance = None

def get_ai_manager_instance():
    """获取 AI 管理器实例（延迟初始化）"""
    global _ai_manager_instance
    if _ai_manager_instance is None:
        _ai_manager_instance = get_ai_manager()
    return _ai_manager_instance

def get_emoji_service_instance():
    """获取表情包服务实例（延迟初始化）"""
    global _emoji_service_instance
    if _emoji_service_instance is None:
        try:
            _emoji_service_instance = get_emoji_service()
        except Exception as e:
            logger.error(f"❌ 表情包服务初始化失败: {e}")
            # 返回 None，调用方需要检查
            return None
    return _emoji_service_instance

def get_message_splitter_instance():
    """获取消息拆分器实例（延迟初始化）"""
    global _message_splitter_instance
    if _message_splitter_instance is None:
        _message_splitter_instance = get_message_splitter()
    return _message_splitter_instance


# ============ 图片处理辅助函数 ============
async def extract_message_content(event: MessageEvent) -> Tuple[str, List[str], List[str], bool]:
    """
    从消息中提取文本和图片 URL
    
    Args:
        event: 消息事件
        
    Returns:
        (纯文本内容, 图片URL列表, 表情包URL列表, 是否有图片)
        
    Note:
        表情包通过 summary 字段识别（如 [动画表情]），普通图片 summary 为空
    """
    text_parts = []
    image_urls = []
    emoji_urls = []  # 只有表情包才加入这个列表
    
    for seg in event.get_message():
        if seg.type == "text":
            text_parts.append(seg.data.get("text", ""))
        elif seg.type == "image":
            url = seg.data.get("url")
            if url:
                image_urls.append(url)
                # 检查 summary 字段，只有包含 "[动画表情]" 的才是表情包
                summary = seg.data.get("summary", "")
                if "[动画表情]" in summary:  # 明确检查是否为动画表情
                    emoji_urls.append(url)
    
    raw_text = "".join(text_parts).strip()
    has_image = len(image_urls) > 0
    
    return raw_text, image_urls, emoji_urls, has_image


async def build_final_user_text(raw_text: str, image_urls: List[str]) -> str:
    """
    构建最终的用户消息文本（包含图片描述）
    
    Args:
        raw_text: 用户输入的纯文本
        image_urls: 图片 URL 列表
        
    Returns:
        合成后的用户消息，格式如：
        - 纯文本：原样返回
        - 纯图片：[图片描述：xxx]
        - 文本+图片：原文本 [图片描述：xxx]
    """
    if not image_urls:
        return raw_text
    
    # 获取图片描述服务
    vision_service = get_vision_caption_service()
    
    # 检查是否启用
    if not vision_service.enabled:
        return raw_text
    
    # 获取所有图片的描述
    descriptions = await vision_service.describe_images(image_urls)
    
    # 过滤空描述
    valid_descriptions = [d for d in descriptions if d]
    
    if not valid_descriptions:
        return raw_text
    
    # 构建图片描述文本
    if len(valid_descriptions) == 1:
        image_text = f"[图片描述：{valid_descriptions[0]}]"
    else:
        # 多张图片
        parts = [f"[图片{i+1}：{desc}]" for i, desc in enumerate(valid_descriptions)]
        image_text = " ".join(parts)
    
    # 合成最终文本
    if raw_text:
        return f"{raw_text} {image_text}"
    else:
        return image_text

# ============ 指令触发的聊天 ============
# 优先级设为 10，让系统命令（优先级 1-5）先处理
yuki_chat_command = on_command("chat", priority=10, block=True, rule=whitelist_rule)


@yuki_chat_command.handle()
async def handle_chat_command(bot: Bot, event: MessageEvent):
    """处理 /chat 指令"""
    user_id_str = str(event.user_id)
    logger.info(f"📨 收到/chat命令: user={user_id_str}, msg={event.get_plaintext()[:50]}")
    
    try:
        # === 0. 黑名单检查（最高优先级）===
        temp_blacklist = get_temp_blacklist()
        user_id_str = str(event.user_id)
        
        if temp_blacklist.is_blocked(user_id_str):
            info = temp_blacklist.get_info(user_id_str)
            if info:
                logger.warning(f"🚫 用户 {user_id_str} 在黑名单中，剩余 {info['remaining_minutes']} 分钟")
                await yuki_chat_command.finish(
                    f"抱歉，您的对话功能已被暂时限制，剩余 {info['remaining_minutes']} 分钟。"
                )
            return  # 已在黑名单，静默拒绝
        
        # === 1. 提取纯文本消息（用于快速审查）===
        raw_text, image_urls, emoji_urls, has_image = await extract_message_content(event)
        
        # === 2. Injection Guard 检查（优先级最高，在任何处理之前）===
        bot_config = ConfigManager.get_bot_config()
        guard_config = bot_config.injection_guard
        
        # 如果有文本内容，立即审查
        if raw_text:
            should_check_guard = (
                guard_config.enable and
                len(raw_text) >= guard_config.skip_short_message_length
            )
            
            if should_check_guard:
                try:
                    injection_guard = get_injection_guard()
                    is_injection = await injection_guard.check(raw_text, user_id_str)
                    
                    if is_injection:
                        # 拉入小黑屋
                        result = temp_blacklist.ban(
                            user_id_str,
                            guard_config.blacklist_minutes,
                            f"疑似注入攻击：{raw_text[:30]}"
                        )
                        # 发送提示消息（不暴露具体原因）
                        await yuki_chat_command.finish(
                            f"抱歉，检测到异常请求，已暂时限制对话功能 {result['remaining_minutes']} 分钟。"
                        )
                except FinishedException:
                    # NoneBot 的正常流程控制异常，需要重新抛出
                    raise
                except Exception as e:
                    # Guard 调用失败，记录错误但继续处理（不阻断用户消息）
                    logger.warning(f"⚠️ Guard 检查失败，跳过审查继续处理: {type(e).__name__}")
                    # 不再finish，让消息继续处理
        
        # === 3. 记录收到消息统计 ===
        from src.services.stats_service import get_stats_service
        stats_service = get_stats_service()
        stats_service.record_incoming_message(str(event.user_id))
        
        # === 4. 表情包学习逻辑（只学习真正的表情包，不学习普通图片）===
        emoji_service = get_emoji_service_instance()
        if emoji_service:  # 检查服务是否可用
            for url in emoji_urls:  # 只处理有 summary 标记的表情包
                asyncio.create_task(emoji_service.save_emoji(url))
        
        # === 5. 构建最终用户消息（包含图片描述）===
        if not raw_text and not has_image:
            await yuki_chat_command.finish("请输入要聊天的内容")
        
        # 如果有图片，获取图片描述并合成最终文本（排除表情包）
        non_emoji_images = [url for url in image_urls if url not in emoji_urls]
        msg_text = await build_final_user_text(raw_text, non_emoji_images)
        
        # 如果最终文本为空（图片识别失败且无文字），跳过
        if not msg_text:
            if has_image:
                return  # 只有图片但识别失败，静默返回
            await yuki_chat_command.finish("请输入要聊天的内容")
        
        # === 6. 区分群聊和私聊，获取用户名 ===
        if isinstance(event, GroupMessageEvent):
            user_id = event.user_id
            group_id = event.group_id
            # 优先使用群名片，其次昵称，最后 QQ 号
            user_name = event.sender.card or event.sender.nickname or str(user_id)
        else:
            user_id = event.user_id
            group_id = None
            # 私聊优先使用昵称，其次 QQ 号
            user_name = event.sender.nickname or str(user_id)
        
        logger.info(f"处理命令: user={user_id}({user_name}), group={group_id}, msg={msg_text[:50]}")
        
        # 获取群名（群聊时）
        group_name = None
        if group_id:
            try:
                group_info = await bot.get_group_info(group_id=group_id)
                group_name = group_info.get("group_name", str(group_id))
            except Exception:
                group_name = str(group_id)
        
        # 调用 AI 管理器，传递用户名称和 ID（用于 RAG）
        ai_manager = get_ai_manager_instance()
        
        # 如果没有短期内存，启动后台任务加载历史（不阻塞响应）
        memory_key = str(group_id) if group_id else str(user_id)
        if not ai_manager.has_short_term_memory(memory_key):
            asyncio.create_task(load_history_async(bot, ai_manager, str(user_id), str(group_id) if group_id else None))
        
        reply = await ai_manager.chat(
            msg_text, user_name, user_id=str(user_id),
            group_id=str(group_id) if group_id else None,
            group_name=group_name
        )
        logger.info(f"✅ 命令AI回复（{len(reply)}字）: {reply[:100]}")
        
        # 使用消息拆分器分段发送，实现拟人化效果
        segment_count = 0
        async for segment in get_message_splitter_instance().process_and_wait(reply):
            if segment:
                segment_count += 1
                logger.debug(f"   发送第{segment_count}段: {segment[:50]}")
                await yuki_chat_command.send(segment)
        
        logger.info(f"✅ 命令处理完成，共发送{segment_count}段消息")
        
        # === 记录发送消息统计 ===
        stats_service.record_outgoing_message(str(user_id))
        
        # === 3. 表情包发送逻辑（智能概率）===
        emoji_config = ConfigManager.get_bot_config().emoji
        if emoji_config.enable_sending:
            # 使用用户的输入去匹配表情
            emoji_service = get_emoji_service_instance()
            if emoji_service:  # 检查服务是否可用
                result = emoji_service.search_emoji(msg_text)
                
                if result:
                    sticker_path, similarity = result
                    should_send = False
                    
                    # 高相似度：直接发送
                    if similarity >= emoji_config.high_similarity_threshold:
                        should_send = True
                        logger.info(f"📤 高相似度 ({similarity:.2%})，直接发送表情")
                    # 低相似度：概率发送
                    elif random.random() < emoji_config.sending_probability:
                        should_send = True
                        logger.info(f"📤 低相似度 ({similarity:.2%})，概率触发发送表情")
                    
                    if should_send:
                        # 检查文件是否存在
                        path_obj = Path(sticker_path)
                        if path_obj.exists():
                            # 模拟找图的延迟
                            await asyncio.sleep(emoji_config.send_delay)
                            # 发送图片
                            await yuki_chat_command.send(MessageSegment.image(path_obj))
    
    except FinishedException:
        # FinishedException 是 NoneBot 正常流程，不需要处理
        raise
    except Exception as e:
        logger.error(f"处理命令时出错: {type(e).__name__}: {e}", exc_info=True)
        try:
            await yuki_chat_command.finish("哎呀，出错了，请稍后再试")
        except FinishedException:
            raise
        except Exception as finish_error:
            logger.error(f"finish() 也出错了: {finish_error}")
            # 最后的兜底：尝试直接发送
            try:
                await yuki_chat_command.send("系统错误")
            except Exception:
                pass


# ============ @机器人的消息 ============
# 使用组合规则：@我 AND 在白名单 AND 不是命令
yuki_mention = on_message(rule=to_me() & chat_rule, priority=10, block=True)


@yuki_mention.handle()
async def handle_mention(bot: Bot, event: MessageEvent):
    """处理 @机器人 的消息"""
    user_id_str = str(event.user_id)
    group_id_str = str(getattr(event, 'group_id', 'N/A'))
    logger.info(f"📨 收到@提及: user={user_id_str}, group={group_id_str}, msg={event.get_plaintext()[:50]}")
    
    try:
        # === 0. 黑名单检查（最高优先级）===
        temp_blacklist = get_temp_blacklist()
        user_id_str = str(event.user_id)
        
        if temp_blacklist.is_blocked(user_id_str):
            info = temp_blacklist.get_info(user_id_str)
            if info:
                logger.warning(f"🚫 用户 {user_id_str} 在黑名单中，剩余 {info['remaining_minutes']} 分钟")
                await yuki_mention.finish(
                    f"抱歉，您的对话功能已被暂时限制，剩余 {info['remaining_minutes']} 分钟。"
                )
            return  # 已在黑名单，静默拒绝
        
        # === 1. 提取纯文本消息（用于快速审查）===
        raw_text, image_urls, emoji_urls, has_image = await extract_message_content(event)
        
        # 移除可能的机器人昵称
        bot_config = ConfigManager.get_bot_config()
        for nickname in [bot_config.nickname] + bot_config.command_start:
            if raw_text.startswith(nickname):
                raw_text = raw_text[len(nickname):].strip()
        
        # === 2. Injection Guard 检查（优先级最高，在任何处理之前）===
        guard_config = bot_config.injection_guard
        
        # 如果有文本内容，立即审查
        if raw_text:
            should_check_guard = (
                guard_config.enable and
                len(raw_text) >= guard_config.skip_short_message_length
            )
            
            if should_check_guard:
                try:
                    injection_guard = get_injection_guard()
                    is_injection = await injection_guard.check(raw_text, user_id_str)
                    
                    if is_injection:
                        # 拉入小黑屋
                        result = temp_blacklist.ban(
                            user_id_str,
                            guard_config.blacklist_minutes,
                            f"疑似注入攻击：{raw_text[:30]}"
                        )
                        # 发送提示消息（不暴露具体原因）
                        await yuki_mention.finish(
                            f"抱歉，检测到异常请求，已暂时限制对话功能 {result['remaining_minutes']} 分钟。"
                        )
                except FinishedException:
                    # NoneBot 的正常流程控制异常，需要重新抛出
                    raise
                except Exception as e:
                    # Guard 调用失败，记录错误但继续处理（不阻断用户消息）
                    logger.warning(f"⚠️ Guard 检查失败，跳过审查继续处理: {type(e).__name__}")
                    # 不再finish，让消息继续处理
        
        # === 3. 记录收到消息统计 ===
        from src.services.stats_service import get_stats_service
        stats_service = get_stats_service()
        stats_service.record_incoming_message(str(event.user_id))
        
        # === 4. 表情包学习逻辑（只学习真正的表情包）===
        emoji_service = get_emoji_service_instance()
        if emoji_service:  # 检查服务是否可用
            for url in emoji_urls:
                asyncio.create_task(emoji_service.save_emoji(url))
        
        # === 5. 构建最终用户消息（包含图片描述）===
        if not raw_text and not has_image:
            await yuki_mention.finish("呃，你是要和我聊天吗？请说点什么吧~")
        
        # 如果有图片，获取图片描述并合成最终文本（排除表情包）
        non_emoji_images = [url for url in image_urls if url not in emoji_urls]
        msg_text = await build_final_user_text(raw_text, non_emoji_images)
        
        # 如果最终文本为空（图片识别失败且无文字），跳过
        if not msg_text:
            if has_image:
                return  # 只有图片但识别失败，静默返回
            await yuki_mention.finish("呃，你是要和我聊天吗？请说点什么吧~")
        
        # === 6. 区分群聊和私聊，获取用户名 ===
        if isinstance(event, GroupMessageEvent):
            user_id = event.user_id
            group_id = event.group_id
            # 优先使用群名片，其次昵称，最后 QQ 号
            user_name = event.sender.card or event.sender.nickname or str(user_id)
        else:
            user_id = event.user_id
            group_id = None
            # 私聊优先使用昵称，其次 QQ 号
            user_name = event.sender.nickname or str(user_id)
        
        logger.info(f"@提及处理: user={user_id}({user_name}), group={group_id}, msg={msg_text[:50]}")
        
        # 获取群名（群聊时）
        group_name = None
        if group_id:
            try:
                group_info = await bot.get_group_info(group_id=group_id)
                group_name = group_info.get("group_name", str(group_id))
            except Exception:
                group_name = str(group_id)
        
        # 调用 AI 管理器，传递用户名称和 ID（用于 RAG）
        ai_manager = get_ai_manager_instance()
        
        # 如果没有短期内存，启动后台任务加载历史（不阻塞响应）
        memory_key = str(group_id) if group_id else str(user_id)
        if not ai_manager.has_short_term_memory(memory_key):
            asyncio.create_task(load_history_async(bot, ai_manager, str(user_id), str(group_id) if group_id else None))
        
        reply = await ai_manager.chat(
            msg_text, user_name, user_id=str(user_id),
            group_id=str(group_id) if group_id else None,
            group_name=group_name
        )
        logger.info(f"✅ @提及AI回复（{len(reply)}字）: {reply[:100]}")
        
        # 使用消息拆分器分段发送，实现拟人化效果
        segment_count = 0
        async for segment in get_message_splitter_instance().process_and_wait(reply):
            if segment:
                segment_count += 1
                logger.debug(f"   发送第{segment_count}段: {segment[:50]}")
                await yuki_mention.send(segment)
        
        logger.info(f"✅ @提及处理完成，共发送{segment_count}段消息")
        
        # === 记录发送消息统计 ===
        stats_service.record_outgoing_message(str(user_id))
        
        # === 3. 表情包发送逻辑（智能概率）===
        emoji_config = ConfigManager.get_bot_config().emoji
        if emoji_config.enable_sending:
            emoji_service = get_emoji_service_instance()
            if emoji_service:  # 检查服务是否可用
                result = emoji_service.search_emoji(msg_text)
                
                if result:
                    sticker_path, similarity = result
                    should_send = False
                    
                    # 高相似度：直接发送
                    if similarity >= emoji_config.high_similarity_threshold:
                        should_send = True
                        logger.info(f"📤 高相似度 ({similarity:.2%})，直接发送表情")
                    # 低相似度：概率发送
                    elif random.random() < emoji_config.sending_probability:
                        should_send = True
                        logger.info(f"📤 低相似度 ({similarity:.2%})，概率触发发送表情")
                    
                    if should_send and Path(sticker_path).exists():
                        await asyncio.sleep(emoji_config.send_delay)
                        await yuki_mention.send(MessageSegment.image(Path(sticker_path)))
    
    except FinishedException:
        # FinishedException 是 NoneBot 正常流程，不需要处理
        raise
    except Exception as e:
        logger.error(f"处理@提及时出错: {type(e).__name__}: {e}", exc_info=True)
        try:
            await yuki_mention.finish("哎呀，出错了，请稍后再试")
        except FinishedException:
            raise
        except Exception as finish_error:
            logger.error(f"finish() 也出错了: {finish_error}")
            # 最后的兜底：尝试直接发送
            try:
                await yuki_mention.send("系统错误")
            except Exception:
                pass


# ============ 私聊直接对话 ============
# 私聊：白名单用户发什么都回复（不需要 @）
# 群聊：必须 @ 机器人，由上面的 yuki_mention 处理
async def is_private_message(event: MessageEvent) -> bool:
    """检查是否是私聊消息"""
    return isinstance(event, PrivateMessageEvent)

try:
    yuki_private_chat = on_message(priority=100, block=True, rule=chat_rule & Rule(is_private_message))
    
    @yuki_private_chat.handle()
    async def handle_private_chat(bot: Bot, event: PrivateMessageEvent):
        """处理私聊消息"""
        user_id_str = str(event.user_id)
        logger.info(f"📨 收到私聊消息: user={user_id_str}, msg={event.get_plaintext()[:50]}")
        
        try:
            # === 0. 黑名单检查（最高优先级）===
            temp_blacklist = get_temp_blacklist()
            user_id_str = str(event.user_id)
            
            if temp_blacklist.is_blocked(user_id_str):
                info = temp_blacklist.get_info(user_id_str)
                if info:
                    logger.warning(f"🚫 用户 {user_id_str} 在黑名单中，剩余 {info['remaining_minutes']} 分钟")
                    await yuki_private_chat.finish(
                        f"抱歉，您的对话功能已被暂时限制，剩余 {info['remaining_minutes']} 分钟。"
                    )
                return  # 已在黑名单，静默拒绝
            
            # === 1. 提取纯文本消息（用于快速审查）===
            raw_text, image_urls, emoji_urls, has_image = await extract_message_content(event)
            
            # === 2. Injection Guard 检查（优先级最高，在任何处理之前）===
            bot_config = ConfigManager.get_bot_config()
            guard_config = bot_config.injection_guard
            
            # 如果有文本内容，立即审查
            if raw_text:
                should_check_guard = (
                    guard_config.enable and
                    len(raw_text) >= guard_config.skip_short_message_length
                )
                
                if should_check_guard:
                    try:
                        injection_guard = get_injection_guard()
                        is_injection = await injection_guard.check(raw_text, user_id_str)
                        
                        if is_injection:
                            # 拉入小黑屋
                            result = temp_blacklist.ban(
                                user_id_str,
                                guard_config.blacklist_minutes,
                                f"疑似注入攻击：{raw_text[:30]}"
                            )
                            # 发送提示消息（不暴露具体原因）
                            await yuki_private_chat.finish(
                                f"抱歉，检测到异常请求，已暂时限制对话功能 {result['remaining_minutes']} 分钟。"
                            )
                    except FinishedException:
                        # NoneBot 的正常流程控制异常，需要重新抛出
                        raise
                    except Exception as e:
                        # Guard 调用失败，记录错误但继续处理（不阻断用户消息）
                        logger.warning(f"⚠️ Guard 检查失败，跳过审查继续处理: {type(e).__name__}")
                        # 不再finish，让消息继续处理
            
            # === 3. 记录收到消息统计 ===
            from src.services.stats_service import get_stats_service
            stats_service = get_stats_service()
            stats_service.record_incoming_message(str(event.user_id))
            
            # === 4. 表情包学习逻辑（只学习真正的表情包）===
            emoji_service = get_emoji_service_instance()
            if emoji_service:  # 检查服务是否可用
                for url in emoji_urls:
                    asyncio.create_task(emoji_service.save_emoji(url))
            
            # === 5. 构建最终用户消息（包含图片描述）===
            if not raw_text and not has_image:
                return  # 私聊空消息直接忽略
            
            # 如果有图片，获取图片描述并合成最终文本（排除表情包）
            non_emoji_images = [url for url in image_urls if url not in emoji_urls]
            msg_text = await build_final_user_text(raw_text, non_emoji_images)
            
            # 如果最终文本为空（图片识别失败且无文字），跳过
            if not msg_text:
                return
            
            # === 6. 获取用户信息 ===
            user_id = event.user_id
            user_name = event.sender.nickname or str(user_id)
            
            logger.info(f"私聊对话: user={user_id}({user_name}), msg={msg_text[:50]}")
            
            # 调用 AI 管理器
            ai_manager = get_ai_manager_instance()
            
            # 如果没有短期内存，启动后台任务加载历史（不阻塞响应）
            if not ai_manager.has_short_term_memory(str(user_id)):
                asyncio.create_task(load_history_async(bot, ai_manager, str(user_id), None))
            
            reply = await ai_manager.chat(msg_text, user_name, user_id=str(user_id))
            logger.info(f"✅ 私聊AI回复（{len(reply)}字）: {reply[:100]}")
            
            # 使用消息拆分器分段发送
            segment_count = 0
            async for segment in get_message_splitter_instance().process_and_wait(reply):
                if segment:
                    segment_count += 1
                    logger.debug(f"   发送第{segment_count}段: {segment[:50]}")
                    await yuki_private_chat.send(segment)
            
            logger.info(f"✅ 私聊处理完成，共发送{segment_count}段消息")
            
            # === 记录发送消息统计 ===
            stats_service.record_outgoing_message(str(user_id))
            
            # === 3. 表情包发送逻辑 ===
            emoji_config = ConfigManager.get_bot_config().emoji
            if emoji_config.enable_sending:
                emoji_service = get_emoji_service_instance()
                if emoji_service:  # 检查服务是否可用
                    result = emoji_service.search_emoji(msg_text)
                    
                    if result:
                        sticker_path, similarity = result
                        should_send = False
                        
                        if similarity >= emoji_config.high_similarity_threshold:
                            should_send = True
                            logger.info(f"📤 高相似度 ({similarity:.2%})，直接发送表情")
                        elif random.random() < emoji_config.sending_probability:
                            should_send = True
                            logger.info(f"📤 低相似度 ({similarity:.2%})，概率触发发送表情")
                        
                        if should_send and Path(sticker_path).exists():
                            await asyncio.sleep(emoji_config.send_delay)
                            await yuki_private_chat.send(MessageSegment.image(Path(sticker_path)))
        
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"处理私聊时出错: {e}", exc_info=True)
            try:
                await yuki_private_chat.send("哎呀，出错了，请稍后再试")
            except Exception:
                logger.error("发送错误消息也失败了")
                pass  # 发送失败也无能为力了

except Exception as e:
    logger.warning(f"私聊处理器初始化失败: {e}")
