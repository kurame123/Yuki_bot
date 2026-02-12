"""
歌词总结服务模块
"""
from .lyrics_client import lyrics_client
from .summarizer import lyrics_summarizer

__all__ = ["lyrics_client", "lyrics_summarizer"]
