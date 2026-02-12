"""
Yuki 管理插件
提供管理员指令用于控制机器人
"""
import nonebot
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.exception import FinishedException
from src.core.logger import logger
from src.core.config_manager import ConfigManager
from src.services.ai_manager import get_ai_manager
from src.core.RAGM import get_graph_storage

ai_manager = get_ai_manager()

# ============ 查看机器人状态 ============
yuki_status = on_command("status", priority=5, block=True)


@yuki_status.handle()
async def handle_status(bot: Bot, event: MessageEvent):
    """查看机器人状态"""
    try:
        # 获取用户图谱统计
        user_id = str(event.user_id)
        graph_storage = get_graph_storage()
        graph_stats = graph_storage.get_user_graph_stats(user_id)
        
        status_text = f"""
【Yuki Bot 状态】
✨ 机器人运行正常
双阶段推理引擎已启动

【你的知识图谱】
节点数: {graph_stats['nodes']}
关系数: {graph_stats['edges']}
""".strip()
        
        await yuki_status.finish(status_text)
    
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"查询状态时出错: {e}")
        await yuki_status.finish("查询状态出错了")


# ============ 清除用户记忆 ============
yuki_clear_memory = on_command("clear", priority=5, block=True)


@yuki_clear_memory.handle()
async def handle_clear_memory(bot: Bot, event: MessageEvent):
    """清除用户的对话记忆"""
    try:
        # 只允许管理员使用
        bot_config = ConfigManager.get_bot_config()
        if bot_config.admin_id and event.user_id not in bot_config.admin_id:
            await yuki_clear_memory.finish("你没有权限执行此操作")
        
        await yuki_clear_memory.finish("✨ 本系统无对话记忆，每次都是独立分析")
    
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"清除记忆时出错: {e}")
        await yuki_clear_memory.finish("清除记忆出错了")


# ============ 机器人配置查询 ============
yuki_config = on_command("config", priority=5, block=True)


@yuki_config.handle()
async def handle_config(bot: Bot, event: MessageEvent):
    """查看机器人配置"""
    try:
        # 只允许管理员使用
        bot_config = ConfigManager.get_bot_config()
        if bot_config.admin_id and event.user_id not in bot_config.admin_id:
            await yuki_config.finish("你没有权限执行此操作")
        
        ai_config = ConfigManager.get_ai_config()
        role_config = ConfigManager.get_role_config()
        
        config_text = f"""
【机器人配置】
昵称: {bot_config.nickname}
指令前缀: {', '.join(bot_config.command_start)}
超级用户: {bot_config.admin_id if bot_config.admin_id else '未设置'}

【AI 模型配置 - 双阶段推理】
默认供应商: {ai_config.common.default_provider}
全局超时: {ai_config.common.timeout}s

场景整理模型: {ai_config.organizer.model_name}
  - 温度: {ai_config.organizer.temperature}
  - 最大Token: {ai_config.organizer.max_tokens}
  - 启用: {'是' if ai_config.organizer.enabled else '否'}

回复生成模型: {ai_config.generator.model_name}
  - 温度: {ai_config.generator.temperature}
  - 最大Token: {ai_config.generator.max_tokens}
  - 启用: {'是' if ai_config.generator.enabled else '否'}

【角色扮演】
角色名称: {role_config.persona.name}
说话风格: {role_config.expression.speaking_style}
""".strip()
        
        await yuki_config.finish(config_text)
    
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"查询配置时出错: {e}")
        await yuki_config.finish("查询配置出错了")


# ============ 重新加载配置 ============
yuki_reload_config = on_command("reload", priority=5, block=True)


@yuki_reload_config.handle()
async def handle_reload_config(bot: Bot, event: MessageEvent):
    """重新加载配置文件（热重载）"""
    try:
        # 只允许管理员使用
        bot_config = ConfigManager.get_bot_config()
        if bot_config.admin_id and event.user_id not in bot_config.admin_id:
            await yuki_reload_config.finish("你没有权限执行此操作")
        
        # 重新加载配置
        ConfigManager.reload()
        logger.info(f"配置已由 {event.user_id} 重新加载")
        
        # 重载向量服务配置
        try:
            from src.services.vector_service import get_vector_service
            vector_service = get_vector_service()
            vector_service.reload_config()
        except Exception as e:
            logger.warning(f"向量服务配置重载失败: {e}")
        
        await yuki_reload_config.finish("✨ 配置已重新加载")
    
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"重新加载配置时出错: {e}")
        await yuki_reload_config.finish(f"重新加载失败: {e}")


# 注意：/help 命令已移至 bot_command 插件，避免重复
