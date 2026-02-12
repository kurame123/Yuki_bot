"""
歌词总结命令
/总结 序号 - 总结指定歌曲的歌词
"""
import time
from typing import Dict
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg
from src.core.security import whitelist_rule
from src.core.config_manager import ConfigManager
from src.core.logger import logger

# 复用 Music_plug 的状态管理
from src.plugins.Music_plug.state import make_session_key, get_search_result

# 导入服务
from .services.lyrics_client import lyrics_client
from .services.summarizer import lyrics_summarizer


# 冷却记录：user_id -> last_timestamp
_cooldown_tracker: Dict[str, float] = {}


# /总结 序号
summary_cmd = on_command("总结", priority=5, block=True, rule=whitelist_rule)


@summary_cmd.handle()
async def handle_summary(bot: Bot, event: Event, args: Message = CommandArg()):
    """总结歌词"""
    cfg = ConfigManager.get_musictext_config()
    
    # 检查是否启用
    if not cfg.general.enable:
        await summary_cmd.finish("歌词总结功能未启用")
    
    # 解析参数
    index_str = args.extract_plain_text().strip()
    if not index_str.isdigit():
        await summary_cmd.finish("用法：/总结 序号（例如：/总结 1）")
    
    idx = int(index_str) - 1
    user_id = event.get_user_id()
    
    # 冷却检查
    now = time.time()
    last_time = _cooldown_tracker.get(user_id, 0)
    cooldown = cfg.general.cooldown_seconds
    
    if now - last_time < cooldown:
        remaining = int(cooldown - (now - last_time))
        await summary_cmd.finish(f"请稍等 {remaining} 秒后再试")
    
    # 获取搜索结果缓存
    group_id = getattr(event, "group_id", None)
    session_key = make_session_key(user_id, group_id)
    songs = get_search_result(session_key)
    
    if not songs:
        await summary_cmd.finish("当前没有可用的点歌结果，请先使用 /song 搜索歌曲")
    
    if idx < 0 or idx >= len(songs):
        await summary_cmd.finish(f"序号超出范围（1-{len(songs)}），请重新输入")
    
    chosen = songs[idx]
    logger.info(f"🎵 用户 {user_id} 请求总结歌词: {chosen.title} - {chosen.artist}")
    
    # 发送"正在处理"提示
    await summary_cmd.send("正在获取歌词并总结，请稍候...")
    
    # 获取歌词（QQ 音乐需要用 songmid，网易云用 song_id）
    song_identifier = chosen.songmid if chosen.platform == "qq" and chosen.songmid else chosen.song_id
    lyrics_text, error_msg = await lyrics_client.fetch_lyrics(chosen.platform, song_identifier)
    
    if error_msg:
        await summary_cmd.finish(f"❌ {error_msg}")
    
    if not lyrics_text:
        await summary_cmd.finish("该歌曲暂无歌词或为纯音乐，无法总结")
    
    # 生成总结
    summary = await lyrics_summarizer.summarize(lyrics_text)
    
    if not summary:
        await summary_cmd.finish("生成总结失败，请稍后再试")
    
    # 更新冷却时间
    _cooldown_tracker[user_id] = now
    
    # 返回总结（带上歌名和歌手）
    result = f"🎵 {chosen.title} - {chosen.artist}\n\n{summary}"
    await summary_cmd.finish(result)
