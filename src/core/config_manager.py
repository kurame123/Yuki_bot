"""
配置管理器 - 负责加载和管理所有 TOML 配置文件
"""
import os
from pathlib import Path
from typing import Optional
import toml
from src.models.config_schema import BotConfig, AIModelConfig, RolePlayConfig, FullConfig, MusicConfig, MusicTextConfig
from src.core.logger import logger


class ConfigManager:
    """
    配置管理单例
    
    用法:
        ConfigManager.load()  # 在启动时调用一次
        ConfigManager.get_bot_config()  # 获取机器人配置
        ConfigManager.get_ai_config()   # 获取 AI 模型配置
        ConfigManager.get_role_config() # 获取角色扮演配置
    """
    
    _instance: Optional['ConfigManager'] = None
    _config: Optional[FullConfig] = None
    _music_config: Optional[MusicConfig] = None
    _musictext_config: Optional[MusicTextConfig] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def load(cls) -> None:
        """
        加载所有 TOML 配置文件
        
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
        """
        manager = cls()
        config_dir = Path(__file__).parent.parent.parent / "configs"
        
        # 加载三个配置文件
        bot_config_path = config_dir / "bot_config.toml"
        ai_model_config_path = config_dir / "ai_model_config.toml"
        role_play_config_path = config_dir / "role_play_config.toml"
        
        try:
            # 读取并解析 TOML 文件
            bot_data = toml.load(str(bot_config_path))
            ai_data = toml.load(str(ai_model_config_path))
            role_data = toml.load(str(role_play_config_path))
            
            # 转换为 Pydantic 对象（自动验证）
            # Bot 配置 - 合并顶层的 storage, bot.whitelist 等
            bot_dict = bot_data.get("bot", {})
            
            # 将顶层的 storage 配置合并到 bot.storage
            if "storage" in bot_data:
                bot_dict["storage"] = bot_data["storage"]
            
            bot_config = BotConfig(**bot_dict)
            
            # AI 模型配置（新的双模型结构，支持多供应商）
            ai_config = AIModelConfig(
                providers=ai_data.get("providers", {}),
                common=ai_data.get("common", {}),
                organizer=ai_data.get("organizer", {}),
                kb_organizer=ai_data.get("kb_organizer"),  # 可选，默认 None
                generator=ai_data.get("generator", {}),
                embedding=ai_data.get("embedding", {}),
                vision=ai_data.get("vision", {}),
                vision_caption=ai_data.get("vision_caption"),
                guard=ai_data.get("guard", {}),
                utility=ai_data.get("utility"),
                fallback=ai_data.get("fallback", {})
            )
            
            # 角色扮演配置（新的细化结构）
            role_config = RolePlayConfig(
                persona=role_data.get("persona", {}),
                expression=role_data.get("expression", {}),
                system_prompt_template=role_data.get("system_prompt_template", {})
            )
            
            # 构建完整配置对象
            manager._config = FullConfig(
                bot=bot_config,
                ai_models=ai_config,
                role_play=role_config
            )
            
            logger.info(f"✅ 配置加载成功")
            logger.info(f"   Bot: {bot_config.nickname}")
            logger.info(f"   Providers: {list(ai_config.providers.keys())}")
            logger.info(f"   Organizer: {ai_config.organizer.model_name} ({ai_config.organizer.provider or ai_config.common.default_provider})")
            logger.info(f"   Generator: {ai_config.generator.model_name} ({ai_config.generator.provider or ai_config.common.default_provider})")
            logger.info(f"   Role: {role_config.persona.name}")
            
        except FileNotFoundError as e:
            logger.error(f"❌ 配置文件不存在: {e}")
            raise
        except ValueError as e:
            logger.error(f"❌ 配置格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 加载配置时出错: {e}")
            raise
    
    @classmethod
    def get_bot_config(cls) -> BotConfig:
        """获取机器人配置"""
        manager = cls()
        if manager._config is None:
            raise RuntimeError("配置未加载，请先调用 ConfigManager.load()")
        return manager._config.bot
    
    @classmethod
    def get_ai_config(cls) -> AIModelConfig:
        """获取 AI 模型配置"""
        manager = cls()
        if manager._config is None:
            raise RuntimeError("配置未加载，请先调用 ConfigManager.load()")
        return manager._config.ai_models
    
    @classmethod
    def get_role_config(cls) -> RolePlayConfig:
        """获取角色扮演配置"""
        manager = cls()
        if manager._config is None:
            raise RuntimeError("配置未加载，请先调用 ConfigManager.load()")
        return manager._config.role_play
    
    @classmethod
    def get_full_config(cls) -> FullConfig:
        """获取完整配置对象"""
        manager = cls()
        if manager._config is None:
            raise RuntimeError("配置未加载，请先调用 ConfigManager.load()")
        return manager._config
    
    @classmethod
    def reload(cls) -> None:
        """重新加载配置（用于热重载）"""
        manager = cls()
        manager._config = None
        manager._music_config = None
        manager._musictext_config = None
        cls.load()
        
        # 重置检索策略单例，使其重新加载 retrieval_config.toml
        try:
            from src.services.retrieval_strategy import reset_retrieval_strategy
            reset_retrieval_strategy()
        except ImportError:
            pass
        
        # 重置消息拆分器单例，使其重新加载配置
        try:
            from src.core.message_splitter import reset_message_splitter
            reset_message_splitter()
        except ImportError:
            pass
        
        logger.info("✅ 所有配置已热重载")
    
    @classmethod
    def get_music_config(cls) -> MusicConfig:
        """获取音乐点歌配置"""
        manager = cls()
        if manager._music_config is None:
            # 懒加载音乐配置
            config_dir = Path(__file__).parent.parent.parent / "configs"
            music_config_path = config_dir / "music_config.toml"
            
            if music_config_path.exists():
                try:
                    music_data = toml.load(str(music_config_path))
                    manager._music_config = MusicConfig(
                        general=music_data.get("general", {}),
                        qq=music_data.get("qq", {}),
                        netease=music_data.get("netease", {})
                    )
                    logger.info("✅ 音乐配置加载成功")
                except Exception as e:
                    logger.warning(f"⚠️ 音乐配置加载失败，使用默认配置: {e}")
                    manager._music_config = MusicConfig()
            else:
                logger.warning("⚠️ 音乐配置文件不存在，使用默认配置")
                manager._music_config = MusicConfig()
        
        return manager._music_config
    
    @classmethod
    def get_musictext_config(cls) -> MusicTextConfig:
        """获取歌词总结配置"""
        manager = cls()
        if manager._musictext_config is None:
            # 懒加载歌词总结配置
            config_dir = Path(__file__).parent.parent.parent / "configs"
            musictext_config_path = config_dir / "musictext_config.toml"
            
            if musictext_config_path.exists():
                try:
                    musictext_data = toml.load(str(musictext_config_path))
                    manager._musictext_config = MusicTextConfig(
                        general=musictext_data.get("general", {}),
                        prompt=musictext_data.get("prompt", {}),
                        qq=musictext_data.get("qq", {}),
                        netease=musictext_data.get("netease", {})
                    )
                    logger.info("✅ 歌词总结配置加载成功")
                except Exception as e:
                    logger.warning(f"⚠️ 歌词总结配置加载失败，使用默认配置: {e}")
                    manager._musictext_config = MusicTextConfig()
            else:
                logger.warning("⚠️ 歌词总结配置文件不存在，使用默认配置")
                manager._musictext_config = MusicTextConfig()
        
        return manager._musictext_config
