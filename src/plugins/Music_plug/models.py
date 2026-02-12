"""
歌曲数据模型
"""
from dataclasses import dataclass, field


@dataclass
class SongItem:
    """歌曲信息"""
    title: str
    artist: str
    song_id: str
    platform: str  # "qq" or "netease"
    share_url: str
    audio_url: str = ""  # 音频播放地址
    image_url: str = ""  # 封面图片地址
    songmid: str = ""    # QQ音乐的 songmid
