"""
记忆 GC 插件 - 手动触发记忆清理和压缩

命令：
- /debot: 对所有用户执行 GC（仅管理员）
- /debot <user_id>: 对指定用户执行 GC（仅管理员）

定时任务：
- 每 12 小时自动执行一次全局 GC
"""
import asyncio
from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.exception import FinishedException

from src.core.config_manager import ConfigManager
from src.core.logger import logger
from src.services.memory_gc_service import get_memory_gc_service


# ============ 定时任务 ============
try:
    scheduler = require("nonebot_plugin_apscheduler").scheduler
    
    @scheduler.scheduled_job("interval", hours=12, id="memory_gc_job")
    async def scheduled_memory_gc():
        """每 12 小时自动执行记忆 GC"""
        logger.info("⏰ 定时记忆 GC 开始...")
        gc_service = get_memory_gc_service()
        results = await gc_service.gc_all_users()
        
        total_deleted = sum(r.deleted_count for r in results)
        total_summarized = sum(r.summarized_count for r in results)
        logger.info(f"⏰ 定时 GC 完成: 处理 {len(results)} 用户, 删除 {total_deleted} 条, 压缩 {total_summarized} 条")

    logger.info("✅ 记忆 GC 定时任务已注册 (每 12 小时)")
except Exception as e:
    logger.warning(f"⚠️ 定时任务未启用 (需要 nonebot-plugin-apscheduler): {e}")


# ============ 手动命令 ============
debot_cmd = on_command("debot", priority=5, block=True)


@debot_cmd.handle()
async def handle_debot(bot: Bot, event: MessageEvent):
    """处理 /debot 命令"""
    try:
        # 权限检查
        bot_config = ConfigManager.get_bot_config()
        if bot_config.admin_id and event.user_id not in bot_config.admin_id:
            await debot_cmd.finish("❌ 你没有权限执行此操作")
        
        # 解析参数
        raw_msg = str(event.get_message()).strip()
        # 移除命令前缀
        arg_text = raw_msg.replace("/debot", "").replace("debot", "").strip()
        
        gc_service = get_memory_gc_service()
        
        if not arg_text:
            # 全局 GC
            await debot_cmd.send("🔄 开始全局记忆 GC，请稍候...")
            
            # 异步执行，避免阻塞
            results = await gc_service.gc_all_users()
            
            # 统计结果
            total_users = len(results)
            affected_users = sum(1 for r in results if r.deleted_count > 0 or r.summarized_count > 0)
            total_deleted = sum(r.deleted_count for r in results)
            total_summarized = sum(r.summarized_count for r in results)
            total_summaries = sum(r.summary_generated for r in results)
            
            report = (
                f"✅ 全局 GC 完成\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"处理用户: {total_users} 人\n"
                f"受影响用户: {affected_users} 人\n"
                f"直接删除: {total_deleted} 条\n"
                f"压缩记忆: {total_summarized} 条\n"
                f"生成摘要: {total_summaries} 条"
            )
            
            await debot_cmd.finish(report)
        
        else:
            # 单用户 GC
            user_id = arg_text
            await debot_cmd.send(f"🔄 开始对用户 {user_id} 执行记忆 GC...")
            
            result = await gc_service.gc_user(user_id)
            
            if result.error:
                await debot_cmd.finish(f"❌ GC 失败: {result.error}")
            
            report = (
                f"✅ 用户 {user_id} GC 完成\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"之前: {result.before_count} 条\n"
                f"之后: {result.after_count} 条\n"
                f"直接删除: {result.deleted_count} 条\n"
                f"压缩记忆: {result.summarized_count} 条\n"
                f"生成摘要: {result.summary_generated} 条"
            )
            
            await debot_cmd.finish(report)
    
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"❌ /debot 命令执行失败: {e}")
        await debot_cmd.finish(f"❌ 执行失败: {e}")
