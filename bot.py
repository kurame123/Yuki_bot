"""
Yuki Bot v1.0 启动入口文件
"""
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
load_dotenv(project_root / ".env")

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBoTAdapter
from src.core.config_manager import ConfigManager
from src.core.logger import setup_logger

# 初始化日志
logger = setup_logger(__name__)


# 自定义日志过滤器，屏蔽噪音事件
class NoiseEventFilter(logging.Filter):
    """过滤掉不需要的事件日志"""
    
    def filter(self, record):
        # 过滤掉输入状态通知
        if 'input_status' in record.getMessage():
            return False
        # 过滤掉其他噪音事件（可以根据需要添加）
        noise_patterns = [
            'notice.notify.input_status',
            # 可以添加更多需要过滤的模式
        ]
        for pattern in noise_patterns:
            if pattern in record.getMessage():
                return False
        return True


# 为 NoneBot 的日志添加过滤器
nonebot_logger = logging.getLogger("nonebot")
nonebot_logger.addFilter(NoiseEventFilter())

# 初始化 NoneBot（从 .env 读取配置）
nonebot.init()

# 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBoTAdapter)

# ============ 配置 NoneBot 日志过滤器（屏蔽 Matcher 噪音日志）============
from nonebot.log import logger as nonebot_log, default_filter, default_format


def custom_log_filter(record):
    """自定义日志过滤器，屏蔽 Matcher 相关的噪音日志"""
    msg: str = record["message"]
    
    # 过滤掉 Matcher 将要处理的提示
    if msg.startswith("Event will be handled by Matcher"):
        return False
    # 过滤掉 Matcher 运行完成的提示
    if "Matcher(" in msg and "running complete" in msg:
        return False
    
    # 其他交给 NoneBot 原有的过滤逻辑
    return default_filter(record)


# 移除默认 handler，添加带过滤器的 handler
nonebot_log.remove()
nonebot_log.add(
    sys.stdout,
    level="INFO",
    format=default_format,
    filter=custom_log_filter,
)


# 加载配置
@driver.on_startup
async def on_startup():
    """启动时加载配置"""
    try:
        ConfigManager.load()
        logger.info("✅ 配置加载成功")
        logger.info(f"   机器人昵称: {ConfigManager.get_bot_config().nickname}")
        logger.info(f"   拆分阈值: {ConfigManager.get_bot_config().reply_strategy.split_threshold} 字")
        logger.info(f"   打字速度: {ConfigManager.get_bot_config().reply_strategy.typing_speed} 秒/字")
        
        # 初始化统计服务
        from src.services.stats_service import get_stats_service
        get_stats_service()
        logger.info("✅ 统计服务初始化成功")
        
        # 初始化好感度服务
        from src.core.Affection import get_affection_service
        affection_service = get_affection_service()
        affection_service.init_db()
        logger.info("✅ 好感度服务初始化成功")
        
        # 预初始化表情包服务（避免第一次消息时阻塞）
        try:
            from src.services.emoji_service import get_emoji_service
            get_emoji_service()
            logger.info("✅ 表情包服务预初始化成功")
        except Exception as emoji_err:
            logger.warning(f"⚠️ 表情包服务初始化失败: {emoji_err}")
        
        # 预初始化向量服务（避免第一次消息时阻塞）
        try:
            from src.services.vector_service import get_vector_service
            get_vector_service()
            logger.info("✅ 向量服务预初始化成功")
        except Exception as vec_err:
            logger.warning(f"⚠️ 向量服务初始化失败: {vec_err}")
        
        # 预初始化 AI 管理器
        try:
            from src.services.ai_manager import get_ai_manager
            get_ai_manager()
            logger.info("✅ AI 管理器预初始化成功")
        except Exception as ai_err:
            logger.warning(f"⚠️ AI 管理器初始化失败: {ai_err}")
        
        # 设置 Web 管理后台路由
        try:
            from src.web import setup_web_routes
            app = nonebot.get_app()
            setup_web_routes(app)
        except Exception as web_err:
            logger.warning(f"⚠️ Web 后台初始化失败（可忽略）: {web_err}")
        
        # 设置记忆 GC 定时任务（每 12 小时执行一次）
        try:
            from nonebot import require
            scheduler = require("nonebot_plugin_apscheduler").scheduler
            from src.services.memory_gc_service import get_memory_gc_service
            
            @scheduler.scheduled_job("interval", hours=12, id="memory_gc")
            async def scheduled_memory_gc():
                """定时记忆 GC 任务"""
                logger.info("⏰ 开始定时记忆 GC...")
                gc_service = get_memory_gc_service()
                await gc_service.gc_all_users()
            
            logger.info("✅ 记忆 GC 定时任务已设置（每 12 小时）")
        except Exception as gc_err:
            logger.warning(f"⚠️ 记忆 GC 定时任务设置失败（可忽略）: {gc_err}")
        
        # 设置黑名单清理定时任务（每 10 分钟执行一次）
        try:
            from nonebot import require
            scheduler = require("nonebot_plugin_apscheduler").scheduler
            from src.core.temp_blacklist import get_temp_blacklist
            
            @scheduler.scheduled_job("interval", minutes=10, id="blacklist_cleanup")
            async def scheduled_blacklist_cleanup():
                """定时清理过期黑名单记录"""
                blacklist = get_temp_blacklist()
                deleted = blacklist.cleanup_expired()
                if deleted > 0:
                    logger.info(f"⏰ 定时清理：删除了 {deleted} 条过期黑名单记录")
            
            logger.info("✅ 黑名单清理定时任务已设置（每 10 分钟）")
        except Exception as clean_err:
            logger.warning(f"⚠️ 黑名单清理定时任务设置失败（可忽略）: {clean_err}")
        
        # 设置 RAG 知识图谱清理定时任务（每 4 小时执行一次）
        try:
            from nonebot import require
            scheduler = require("nonebot_plugin_apscheduler").scheduler
            from src.core.RAGM.graph_storage import get_graph_storage
            from src.core.RAGM.ai_graph_cleaner import AIGraphCleaner
            
            @scheduler.scheduled_job("interval", hours=4, id="rag_graph_cleanup")
            async def scheduled_rag_cleanup():
                """定时清理 RAG 知识图谱（使用 AI）"""
                logger.info("⏰ 开始定时 RAG 图谱清理（AI 模式）...")
                
                try:
                    graph_storage = get_graph_storage()
                    cleaner = AIGraphCleaner(graph_storage)
                    
                    # AI 清理前 10 个用户（避免 API 调用过多）
                    result = await cleaner.ai_cleanup_all_users(limit=10)
                    
                    logger.info(f"✅ RAG 图谱清理完成: 处理 {result['users_processed']} 个用户, "
                              f"合并 {result['total_merged']} 个实体, 删除 {result['total_deleted']} 个无用实体")
                except Exception as e:
                    logger.error(f"❌ RAG 图谱清理失败: {e}")
            
            logger.info("✅ RAG 图谱清理定时任务已设置（每 4 小时，AI 模式）")
        except Exception as rag_err:
            logger.warning(f"⚠️ RAG 图谱清理定时任务设置失败（可忽略）: {rag_err}")
        
    except Exception as e:
        logger.error(f"❌ 配置加载失败: {e}")
        raise


# Bot 连接后自动加载历史消息
@driver.on_bot_connect
async def on_bot_connect(bot):
    """Bot 连接后自动加载最近的聊天历史到缓存"""
    try:
        from src.services.ai_manager import get_ai_manager
        from src.services.stats_service import get_stats_service
        
        ai_manager = get_ai_manager()
        stats_service = get_stats_service()
        
        # 获取最近活跃的用户列表（从统计服务）
        active_users = stats_service.get_recent_active_users(limit=20)  # 加载最近 20 个活跃用户
        
        if not active_users:
            logger.info("📭 没有最近活跃的用户，跳过历史加载")
            return
        
        logger.info(f"🔄 开始加载 {len(active_users)} 个活跃用户的历史消息...")
        
        loaded_count = 0
        for user_id in active_users:
            try:
                # 尝试加载私聊历史（200 条，尽可能多地加载到缓存）
                count = await ai_manager.load_history_from_napcat(bot, str(user_id), count=200)
                if count > 0:
                    loaded_count += 1
                    logger.debug(f"   ✓ 用户 {user_id}: {count} 轮对话")
            except Exception as e:
                logger.debug(f"   ✗ 用户 {user_id}: {e}")
                continue
        
        logger.info(f"✅ 历史加载完成: {loaded_count}/{len(active_users)} 个用户")
        
    except Exception as e:
        logger.warning(f"⚠️ 自动加载历史失败（可忽略）: {e}")


# 先加载 alconna 插件（避免加载顺序问题）
try:
    nonebot.load_plugin("nonebot_plugin_alconna")
except Exception as e:
    logger.warning(f"⚠️ nonebot_plugin_alconna 加载失败: {e}")

# 加载所有插件
nonebot.load_plugins("src/plugins")

# 注意：不需要显式加载 manosaba-memes 插件，因为它已经在 src/plugins 中被加载了

if __name__ == "__main__":
    nonebot.run()
