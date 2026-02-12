"""
歌词获取与清洗服务
"""
import re
import httpx
from typing import Optional, Tuple
from src.core.config_manager import ConfigManager
from src.core.logger import logger


class LyricsClient:
    """歌词获取客户端"""
    
    @staticmethod
    async def fetch_lyrics(platform: str, song_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        获取并清洗歌词
        
        Args:
            platform: 平台名称 ("qq" 或 "netease")
            song_id: 歌曲 ID（QQ 为 songmid，网易云为 id）
        
        Returns:
            (lyrics_text, error_msg): 成功返回歌词文本和 None，失败返回 None 和错误信息
        """
        cfg = ConfigManager.get_musictext_config()
        
        if platform == "qq":
            return await LyricsClient._fetch_qq_lyrics(song_id, cfg)
        elif platform == "netease":
            return await LyricsClient._fetch_netease_lyrics(song_id, cfg)
        else:
            return None, f"不支持的平台: {platform}"
    
    @staticmethod
    async def _fetch_qq_lyrics(songmid: str, cfg) -> Tuple[Optional[str], Optional[str]]:
        """获取 QQ 音乐歌词"""
        if not cfg.qq.enable:
            return None, "QQ 音乐歌词接口未启用"
        
        url = f"{cfg.qq.base_url}{cfg.qq.lyrics_path}"
        params = {cfg.qq.songmid_param: songmid}
        
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            
            # QQ 音乐 API 返回格式：{"code": 200, "data": "歌词文本"}
            lyrics_raw = None
            if isinstance(data, dict):
                if data.get("code") == 200:
                    lyrics_raw = data.get("data")
                else:
                    # 如果有错误信息
                    error_msg = data.get("error") or data.get("message") or "未知错误"
                    return None, f"API 返回错误: {error_msg}"
            
            if not lyrics_raw:
                return None, "该歌曲暂无歌词"
            
            # 清洗歌词
            cleaned = LyricsClient._clean_lyrics(lyrics_raw)
            if not cleaned:
                return None, "歌词内容为空或为纯音乐"
            
            return cleaned, None
            
        except httpx.TimeoutException:
            logger.warning(f"QQ 音乐歌词接口超时: {songmid}")
            return None, "获取歌词超时，请稍后再试"
        except Exception as e:
            logger.warning(f"获取 QQ 音乐歌词失败: {e}")
            return None, f"获取歌词失败: {str(e)}"
    
    @staticmethod
    async def _fetch_netease_lyrics(song_id: str, cfg) -> Tuple[Optional[str], Optional[str]]:
        """获取网易云音乐歌词"""
        if not cfg.netease.enable:
            return None, "网易云音乐歌词接口未启用"
        
        url = f"{cfg.netease.base_url}{cfg.netease.lyrics_path}"
        params = {cfg.netease.id_param: song_id}
        
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            
            # 网易云 API 通常返回 lrc.lyric
            lyrics_raw = None
            if isinstance(data, dict):
                lrc_obj = data.get("lrc", {})
                lyrics_raw = lrc_obj.get("lyric")
            
            if not lyrics_raw:
                return None, "该歌曲暂无歌词"
            
            # 清洗歌词
            cleaned = LyricsClient._clean_lyrics(lyrics_raw)
            if not cleaned:
                return None, "歌词内容为空或为纯音乐"
            
            return cleaned, None
            
        except httpx.TimeoutException:
            logger.warning(f"网易云音乐歌词接口超时: {song_id}")
            return None, "获取歌词超时，请稍后再试"
        except Exception as e:
            logger.warning(f"获取网易云音乐歌词失败: {e}")
            return None, f"获取歌词失败: {str(e)}"
    
    @staticmethod
    def _clean_lyrics(raw: str) -> str:
        """
        清洗歌词文本
        
        步骤：
        1. 去除时间戳 [00:12.34]
        2. 去除 LRC 标签 [ti:] [ar:] [al:] 等
        3. 替换 \\n 为真正的换行符
        4. 去除空行和多余空白
        5. 去除作词/作曲等 metadata
        6. 限制长度（防止 token 爆炸）
        """
        if not raw:
            return ""
        
        # 1. 去除时间戳 [00:12.34] 或 [00:12.345]
        text = re.sub(r'\[\d{2}:\d{2}\.\d{2,3}\]', '', raw)
        
        # 2. 去除 LRC 标签 [ti:xxx] [ar:xxx] [al:xxx] [by:xxx] [offset:xxx]
        text = re.sub(r'\[(ti|ar|al|by|offset):[^\]]*\]', '', text)
        
        # 3. 替换 \\n 为真正的换行符
        text = text.replace('\\n', '\n')
        
        # 4. 去除常见的 metadata 行（作词、作曲、编曲等）
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            # 跳过空行
            if not line:
                continue
            # 跳过 metadata 行
            if any(keyword in line for keyword in [
                '作词', '作曲', '编曲', '制作人', '混音', '母带', '录音',
                'by:', 'By:', '词：', '曲：', '版权', '出品', 'Vocal', 'MV'
            ]):
                continue
            cleaned_lines.append(line)
        
        # 5. 合并成文本
        result = '\n'.join(cleaned_lines)
        
        # 6. 限制长度（最多保留 5000 字符，够总结用）
        if len(result) > 5000:
            result = result[:5000]
        
        return result.strip()


# 全局单例
lyrics_client = LyricsClient()
