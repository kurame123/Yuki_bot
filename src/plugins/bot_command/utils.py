"""
Bot 命令工具函数
提供配置写入和热重载功能
"""
import toml
from pathlib import Path
from src.core.config_manager import ConfigManager
from src.core.logger import logger

# 配置文件路径
CONFIG_PATH = Path("configs/bot_config.toml")


def reload_config() -> bool:
    """
    热重载配置
    
    Returns:
        是否成功重载
    """
    try:
        ConfigManager.reload()
        logger.info("✅ 配置已热重载")
        return True
    except Exception as e:
        logger.error(f"❌ 热重载失败: {e}")
        return False


def add_whitelist(target_id: int, mode: str) -> bool:
    """
    修改配置文件并写入磁盘
    
    Args:
        target_id: 目标 ID（群号或 QQ 号）
        mode: 'group' 或 'user'
        
    Returns:
        是否成功添加
    """
    if not CONFIG_PATH.exists():
        logger.error(f"❌ 配置文件不存在: {CONFIG_PATH}")
        return False
    
    try:
        # 1. 读取现有配置
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = toml.load(f)
        
        # 2. 修改数据
        # 确保 bot.whitelist 节点存在
        if "bot" not in data:
            data["bot"] = {}
        if "whitelist" not in data["bot"]:
            data["bot"]["whitelist"] = {
                "enable": True,
                "allow_all_private": False,
                "allowed_users": [],
                "allowed_groups": []
            }
        
        whitelist = data["bot"]["whitelist"]
        
        if mode == 'group':
            # 检查是否已存在
            if target_id in whitelist.get("allowed_groups", []):
                logger.info(f"ℹ️  群 {target_id} 已在白名单中")
                return True
            # 添加到白名单
            whitelist.setdefault("allowed_groups", []).append(target_id)
            logger.info(f"➕ 添加群 {target_id} 到白名单")
            
        elif mode == 'user':
            # 检查是否已存在
            if target_id in whitelist.get("allowed_users", []):
                logger.info(f"ℹ️  用户 {target_id} 已在白名单中")
                return True
            # 添加到白名单
            whitelist.setdefault("allowed_users", []).append(target_id)
            logger.info(f"➕ 添加用户 {target_id} 到白名单")
        else:
            logger.error(f"❌ 未知模式: {mode}")
            return False
        
        # 3. 写回文件
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            toml.dump(data, f)
        
        logger.info(f"✅ 配置文件已更新")
        
        # 4. 触发重载
        return reload_config()
        
    except Exception as e:
        logger.error(f"❌ 写入配置失败: {e}")
        return False


def get_whitelist_info() -> dict:
    """
    获取白名单信息
    
    Returns:
        白名单统计信息
    """
    try:
        config = ConfigManager.get_bot_config()
        return {
            "enabled": config.whitelist.enable,
            "allow_all_private": config.whitelist.allow_all_private,
            "user_count": len(config.whitelist.allowed_users),
            "group_count": len(config.whitelist.allowed_groups),
            "users": config.whitelist.allowed_users,
            "groups": config.whitelist.allowed_groups
        }
    except Exception as e:
        logger.error(f"❌ 获取白名单信息失败: {e}")
        return {}
