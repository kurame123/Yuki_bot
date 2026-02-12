"""
安全和权限控制模块
提供白名单、黑名单等准入控制功能
"""
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import Rule
from src.core.config_manager import ConfigManager
from src.core.logger import logger

# 用于缓存本次事件的白名单检查结果，避免重复日志
_whitelist_cache: dict[str, bool] = {}


async def check_whitelist(event: Event) -> bool:
    """
    白名单核心检查逻辑
    
    Args:
        event: NoneBot 事件对象
        
    Returns:
        True 表示通过（允许处理），False 表示拦截
    """
    global _whitelist_cache
    
    # 生成缓存 key（基于事件 ID，同一条消息只检查一次）
    try:
        event_id = str(id(event))
    except:
        event_id = None
    
    # 如果已经检查过这个事件，直接返回缓存结果
    if event_id and event_id in _whitelist_cache:
        return _whitelist_cache[event_id]
    
    # 清理旧缓存（保留最近 100 条）
    if len(_whitelist_cache) > 100:
        _whitelist_cache.clear()
    
    try:
        user_id = int(event.get_user_id())
        
        # 0. 超级用户特权：直接放行
        superusers = get_driver().config.superusers
        if str(user_id) in superusers:
            logger.debug(f"✅ 超级用户 {user_id} 放行")
            if event_id:
                _whitelist_cache[event_id] = True
            return True
        
        # 获取白名单配置
        config = ConfigManager.get_bot_config().whitelist
        
        # 1. 如果白名单功能没开，直接放行
        if not config.enable:
            logger.debug(f"✅ 白名单未启用，放行 {user_id}")
            if event_id:
                _whitelist_cache[event_id] = True
            return True
        
        # 2. 检查私聊
        if isinstance(event, PrivateMessageEvent):
            # 如果允许所有私聊，或者用户在白名单里
            if config.allow_all_private:
                logger.debug(f"✅ 允许所有私聊，放行 {user_id}")
                if event_id:
                    _whitelist_cache[event_id] = True
                return True
            
            if user_id in config.allowed_users:
                logger.debug(f"✅ 用户 {user_id} 在白名单中，放行")
                if event_id:
                    _whitelist_cache[event_id] = True
                return True
            
            logger.warning(f"🚫 用户 {user_id} 不在白名单中，拦截私聊")
            if event_id:
                _whitelist_cache[event_id] = False
            return False
        
        # 3. 检查群聊（群在白名单里，群内所有人都可以用）
        if isinstance(event, GroupMessageEvent):
            group_id = event.group_id
            
            # 只检查群是否在白名单，不检查用户
            if group_id in config.allowed_groups:
                logger.debug(f"✅ 群 {group_id} 在白名单中，用户 {user_id} 放行")
                if event_id:
                    _whitelist_cache[event_id] = True
                return True
            
            logger.warning(f"🚫 群 {group_id} 不在白名单中，拦截消息（用户: {user_id}）")
            if event_id:
                _whitelist_cache[event_id] = False
            return False
        
        # 其他类型的事件，默认拦截
        logger.warning(f"🚫 未知事件类型，拦截")
        if event_id:
            _whitelist_cache[event_id] = False
        return False
        
    except Exception as e:
        logger.error(f"❌ 白名单检查失败: {e}")
        # 出错时默认拦截，保证安全
        return False


# 导出为一个 Nonebot Rule 对象
whitelist_rule = Rule(check_whitelist)
