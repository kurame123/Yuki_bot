"""
测试历史消息加载的管理员命令
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.exception import FinishedException
from src.core.logger import logger
from src.core.config_manager import ConfigManager


# 测试历史消息加载
test_history = on_command("test_history", priority=5, block=True)


@test_history.handle()
async def handle_test_history(bot: Bot, event: MessageEvent):
    """测试加载历史消息"""
    try:
        # 只允许管理员使用
        bot_config = ConfigManager.get_bot_config()
        if bot_config.admin_id and event.user_id not in bot_config.admin_id:
            await test_history.finish("你没有权限执行此操作")
        
        user_id = str(event.user_id)
        
        # 获取 Bot 自己的 QQ 号
        bot_info = await bot.get_login_info()
        bot_qq_id = str(bot_info.get("user_id", ""))
        
        result_lines = [f"📊 历史消息加载测试 (User: {user_id})"]
        result_lines.append(f"Bot QQ: {bot_qq_id}")
        result_lines.append("")
        
        # 测试不同的消息数量
        for count in [20, 50, 100]:
            try:
                # 调用 NapCat API 获取私聊历史
                history = await bot.get_friend_msg_history(user_id=int(user_id), count=count)
                messages = history.get("messages", [])
                
                if not messages:
                    result_lines.append(f"❌ 请求 {count} 条: 未获取到消息")
                    continue
                
                # 按时间排序
                messages.sort(key=lambda m: m.get("time", 0))
                
                # 统计
                user_msgs = 0
                bot_msgs = 0
                command_msgs = 0
                empty_msgs = 0
                pairs = []
                pending_query = None
                
                for msg in messages:
                    sender_id = str(msg.get("sender", {}).get("user_id", ""))
                    
                    # 提取纯文本
                    text = ""
                    for seg in msg.get("message", []):
                        if seg.get("type") == "text":
                            text += seg.get("data", {}).get("text", "")
                    
                    text = text.strip()
                    
                    if not text:
                        empty_msgs += 1
                        continue
                    
                    if text.startswith("/"):
                        command_msgs += 1
                        pending_query = None
                        continue
                    
                    if sender_id == bot_qq_id:
                        bot_msgs += 1
                        if pending_query:
                            pairs.append((pending_query, text))
                            pending_query = None
                    else:
                        user_msgs += 1
                        if pending_query:
                            logger.debug(f"用户连续消息")
                        pending_query = text
                
                result_lines.append(f"✅ 请求 {count} 条:")
                result_lines.append(f"   原始: {len(messages)} 条")
                result_lines.append(f"   用户: {user_msgs}, Bot: {bot_msgs}")
                result_lines.append(f"   命令: {command_msgs}, 空: {empty_msgs}")
                result_lines.append(f"   配对: {len(pairs)} 轮")
                result_lines.append("")
                
            except Exception as e:
                result_lines.append(f"❌ 请求 {count} 条失败: {e}")
                result_lines.append("")
        
        await test_history.finish("\n".join(result_lines))
        
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"测试历史消息失败: {e}", exc_info=True)
        await test_history.finish(f"测试失败: {e}")
