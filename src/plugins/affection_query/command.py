"""
好感度查询命令插件
独立于对话流程，只通过 AffectionService 访问数据
"""
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import MessageEvent
from src.core.security import whitelist_rule
from src.core.logger import logger


# 注册命令：/好感度
# 群聊需要 @ 触发，私聊直接触发
affection_cmd = on_command(
    "好感度",
    aliases={"affection", "好感"},
    priority=5,
    block=True,
    rule=whitelist_rule
)


@affection_cmd.handle()
async def handle_affection_query(event: MessageEvent):
    """处理好感度查询命令"""
    from nonebot.exception import FinishedException
    
    try:
        from src.core.Affection import get_affection_service
        
        user_id = str(event.get_user_id())
        affection_service = get_affection_service()
        
        info = affection_service.get_affection_info_for_display(user_id)
        
        # 构建回复文本
        score = info["score"]
        level = info["level"]
        level_name = info["level_name"]
        interactions = info["total_interactions"]
        
        # 等级进度条
        progress = "●" * level + "○" * (8 - level)
        
        reply_text = (
            f"💕 当前你与 Yuki 的好感度\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 分数：{score} / 10.0\n"
            f"🏷️ 等级：{level_name}（第 {level} 阶）\n"
            f"📈 进度：[{progress}]\n"
            f"💬 互动次数：{interactions} 次"
        )
        
        await affection_cmd.finish(reply_text)
    
    except FinishedException:
        # NoneBot 正常流程，直接抛出
        raise
    except Exception as e:
        logger.error(f"好感度查询失败: {e}")
        await affection_cmd.finish("查询好感度时出错了，请稍后再试~")
