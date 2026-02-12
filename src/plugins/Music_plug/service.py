"""
音乐搜索服务
封装 NeteaseCloudMusicApi / QQ 音乐 API 调用
"""
import httpx
from typing import List
from src.core.config_manager import ConfigManager
from src.core.logger import logger
from .models import SongItem


class MusicService:
    """音乐搜索服务"""
    
    def __init__(self):
        self.config = ConfigManager.get_music_config()
    
    async def search(self, keyword: str) -> List[SongItem]:
        """根据配置中的 default_platform 进行搜索"""
        platform = self.config.general.default_platform
        
        if platform == "netease":
            return await self._search_netease(keyword)
        elif platform == "qq":
            return await self._search_qq(keyword)
        else:
            return []
    
    async def _search_netease(self, keyword: str) -> List[SongItem]:
        """网易云音乐搜索 (使用 NeteaseCloudMusicApi)"""
        cfg = self.config.netease
        if not cfg.enable or not cfg.base_url:
            logger.warning("网易云音乐未配置或未启用")
            return []
        
        url = cfg.base_url.rstrip("/") + cfg.search_path  # /cloudsearch
        params = {"keywords": keyword, "limit": 6}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            
            songs_data = data.get("result", {}).get("songs", []) or []
            results: List[SongItem] = []
            
            for s in songs_data[:6]:
                song_id = str(s.get("id"))
                title = s.get("name", "未知歌曲")
                # NeteaseCloudMusicApi 返回字段是 "ar"
                artists = s.get("ar") or s.get("artists") or []
                artist_name = "、".join(a.get("name", "") for a in artists if a.get("name")) or "未知歌手"
                share_url = f"https://music.163.com/#/song?id={song_id}"
                
                results.append(SongItem(
                    title=title,
                    artist=artist_name,
                    song_id=song_id,
                    platform="netease",
                    share_url=share_url,
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"网易云搜索失败: {e}")
            return []
    
    async def _search_qq(self, keyword: str) -> List[SongItem]:
        """QQ 音乐搜索"""
        cfg = self.config.qq
        if not cfg.enable or not cfg.base_url or not cfg.search_path:
            logger.warning("QQ 音乐未配置或未启用")
            return []
        
        base_url = cfg.base_url.rstrip("/")
        url = base_url + cfg.search_path
        params = {"keyword": keyword, "limit": 6}
        headers = {}
        if cfg.auth_token:
            headers["Authorization"] = f"Bearer {cfg.auth_token}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            
            songs_data = data.get("data", {}).get("list", []) or []
            results: List[SongItem] = []
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                for s in songs_data[:6]:
                    song_id = str(s.get("songid") or s.get("id"))
                    songmid = s.get("songmid", "")
                    albummid = s.get("albummid", "")
                    title = s.get("songname") or s.get("name") or "未知歌曲"
                    singer_list = s.get("singer", [])
                    artist_name = "、".join(x.get("name", "") for x in singer_list) or "未知歌手"
                    share_url = f"https://y.qq.com/n/ryqq/songDetail/{songmid}"
                    image_url = f"https://y.qq.com/music/photo_new/T002R300x300M000{albummid}.jpg" if albummid else ""
                    
                    # 获取音频 URL
                    audio_url = ""
                    try:
                        song_resp = await client.get(f"{base_url}/song", params={"songmid": songmid})
                        if song_resp.status_code == 200:
                            song_data = song_resp.json()
                            music_url_data = song_data.get("music_url", {})
                            # music_url 是对象 {"bitrate": "...", "url": "..."}
                            if isinstance(music_url_data, dict):
                                audio_url = music_url_data.get("url", "")
                            else:
                                audio_url = str(music_url_data) if music_url_data else ""
                    except Exception as e:
                        logger.warning(f"获取音频URL失败: {e}")
                    
                    results.append(SongItem(
                        title=title,
                        artist=artist_name,
                        song_id=song_id,
                        platform="qq",
                        share_url=share_url,
                        audio_url=audio_url,
                        image_url=image_url,
                        songmid=songmid,
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"QQ 音乐搜索失败: {e}")
            return []


# 全局服务实例
music_service = MusicService()
