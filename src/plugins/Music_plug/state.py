"""
会话状态管理
保存每个会话的最近一次搜索结果
"""
from typing import Dict, List, Optional
from .models import SongItem

# 搜索结果缓存：key 为 session_key，value 为歌曲列表
_search_cache: Dict[str, List[SongItem]] = {}


def make_session_key(user_id: str, group_id: Optional[int]) -> str:
    """生成会话唯一标识"""
    if group_id:
        return f"group_{group_id}"
    return f"private_{user_id}"


def set_search_result(session_key: str, songs: List[SongItem]) -> None:
    """保存搜索结果到缓存"""
    _search_cache[session_key] = songs


def get_search_result(session_key: str) -> Optional[List[SongItem]]:
    """获取缓存的搜索结果"""
    return _search_cache.get(session_key)
