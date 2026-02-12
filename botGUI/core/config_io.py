"""
配置文件读写模块 - 处理 TOML 和 .env 文件
"""
import re
import sys
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

# Python 3.11+ 内置 tomllib，否则用 tomli
if sys.version_info >= (3, 11):
    import tomllib as tomli
else:
    try:
        import tomli
    except ImportError:
        tomli = None

# tomli_w 用于写入（标准库没有）
try:
    import tomli_w
except ImportError:
    tomli_w = None


@dataclass
class ConfigFile:
    """配置文件信息"""
    name: str
    path: Path
    file_type: str  # "toml" or "env"
    description: str


class ConfigIO:
    """配置文件读写器"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root or self._get_project_root()
        self._configs_dir = self._project_root / "configs"
        self._env_file = self._project_root / ".env"
    
    @staticmethod
    def _get_project_root() -> Path:
        """获取项目根目录，兼容打包后和开发环境"""
        import sys
        if getattr(sys, 'frozen', False):
            # 打包环境：查找包含 bot.py 的目录
            exe_dir = Path(sys.executable).parent
            for candidate in [exe_dir.parent.parent, exe_dir.parent, exe_dir]:
                if (candidate / "bot.py").exists():
                    return candidate
            return exe_dir.parent.parent
        else:
            return Path(__file__).parent.parent.parent
    
    def list_config_files(self) -> list[ConfigFile]:
        """列出所有配置文件"""
        configs = []
        
        # TOML 配置文件
        toml_descriptions = {
            "bot_config.toml": "机器人基础配置（昵称、白名单、回复策略）",
            "ai_model_config.toml": "AI 模型配置（模型名称、温度参数）",
            "role_play_config.toml": "角色扮演配置（人设、表达方式）",
            "web_config.toml": "Web 后台配置（端口、认证）",
            "music_config.toml": "音乐插件配置",
            "retrieval_config.toml": "检索策略配置",
        }
        
        if self._configs_dir.exists():
            for toml_file in self._configs_dir.glob("*.toml"):
                configs.append(ConfigFile(
                    name=toml_file.name,
                    path=toml_file,
                    file_type="toml",
                    description=toml_descriptions.get(toml_file.name, "配置文件")
                ))
        
        # .env 文件
        if self._env_file.exists():
            configs.append(ConfigFile(
                name=".env",
                path=self._env_file,
                file_type="env",
                description="环境变量配置（端口、超级用户、插件设置）"
            ))
        
        return configs
    
    def read_toml(self, filename: str) -> dict[str, Any]:
        """读取 TOML 配置文件"""
        if tomli is None:
            raise ImportError("需要安装 tomli: pip install tomli")
        
        file_path = self._configs_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {filename}")
        
        with open(file_path, "rb") as f:
            return tomli.load(f)
    
    def write_toml(self, filename: str, data: dict[str, Any]):
        """写入 TOML 配置文件"""
        if tomli_w is None:
            raise ImportError("需要安装 tomli-w: pip install tomli-w")
        
        file_path = self._configs_dir / filename
        with open(file_path, "wb") as f:
            tomli_w.dump(data, f)
    
    def read_env(self) -> dict[str, str]:
        """读取 .env 文件"""
        if not self._env_file.exists():
            return {}
        
        env_vars = {}
        with open(self._env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
        
        return env_vars
    
    def write_env(self, updates: dict[str, str]):
        """更新 .env 文件中的指定键值"""
        if not self._env_file.exists():
            return
        
        lines = []
        updated_keys = set()
        
        with open(self._env_file, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        lines.append(f"{key}={updates[key]}\n")
                        updated_keys.add(key)
                        continue
                lines.append(line)
        
        # 添加新的键
        for key, value in updates.items():
            if key not in updated_keys:
                lines.append(f"{key}={value}\n")
        
        with open(self._env_file, "w", encoding="utf-8") as f:
            f.writelines(lines)
    
    def get_bot_port(self) -> int:
        """获取 Bot 监听端口"""
        env = self.read_env()
        return int(env.get("PORT", "8080"))
    
    def get_bot_nickname(self) -> str:
        """获取 Bot 昵称"""
        try:
            config = self.read_toml("bot_config.toml")
            return config.get("bot", {}).get("nickname", "Yuki")
        except Exception:
            return "Yuki"


def get_config_io() -> ConfigIO:
    """获取配置读写器"""
    return ConfigIO()
