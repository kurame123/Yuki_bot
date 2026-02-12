"""
音乐点歌命令
/song <歌名> - 搜索歌曲
/songcon <序号> - 选择歌曲
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
from src.core.security import whitelist_rule
from src.core.config_manager import ConfigManager
from src.core.logger import logger
from .service import music_service
from .state import make_session_key, set_search_result, get_search_result


# /song 歌名
song_cmd = on_command("song", priority=5, block=True, rule=whitelist_rule)


@song_cmd.handle()
async def handle_song(bot: Bot, event: Event, args: Message = CommandArg()):
    """搜索歌曲"""
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await song_cmd.finish("用法：/song 歌名")
    
    logger.info(f"🎵 用户 {event.get_user_id()} 搜索歌曲: {keyword}")
    
    # 搜索
    songs = await music_service.search(keyword)
    if not songs:
        await song_cmd.finish("没有找到相关歌曲，请换个关键词试试。")
    
    # 保存到会话缓存
    group_id = getattr(event, "group_id", None)
    session_key = make_session_key(event.get_user_id(), group_id)
    set_search_result(session_key, songs)

    # 组织列表输出
    cfg = ConfigManager.get_music_config()
    platform = cfg.general.default_platform
    header = "QQ音乐" if platform == "qq" else "网易云音乐"
    
    lines = [f"🎵 {header} 搜索结果："]
    for i, s in enumerate(songs, start=1):
        lines.append(f"{i}. {s.title} - {s.artist}")
    lines.append("\n使用 /songcon 序号 来选择歌曲，例如：/songcon 1")
    
    await song_cmd.finish("\n".join(lines))


# /songcon 序号
songcon_cmd = on_command("songcon", priority=5, block=True, rule=whitelist_rule)


@songcon_cmd.handle()
async def handle_songcon(bot: Bot, event: Event, args: Message = CommandArg()):
    """选择歌曲，发送音乐卡片"""
    index_str = args.extract_plain_text().strip()
    if not index_str.isdigit():
        await songcon_cmd.finish("用法：/songcon 序号（例如：/songcon 1）")
    
    idx = int(index_str) - 1
    group_id = getattr(event, "group_id", None)
    session_key = make_session_key(event.get_user_id(), group_id)
    songs = get_search_result(session_key)
    
    if not songs:
        await songcon_cmd.finish("当前没有可用的点歌结果，请先使用 /song 搜索。")
    
    if idx < 0 or idx >= len(songs):
        await songcon_cmd.finish("序号超出范围，请重新输入。")
    
    chosen = songs[idx]
    logger.info(f"🎵 用户 {event.get_user_id()} 选择歌曲: {chosen.title} - {chosen.artist}")
    
    # 构造音乐卡片
    try:
        if chosen.platform == "qq" and chosen.audio_url:
            # QQ 音乐使用自定义卡片
            seg = MessageSegment(
                type="music",
                data={
                    "type": "custom",
                    "url": chosen.share_url,
                    "audio": chosen.audio_url,
                    "title": chosen.title,
                    "content": chosen.artist,
                    "image": chosen.image_url or "https://y.qq.com/mediastyle/global/img/album_300.png"
                }
            )
            await songcon_cmd.finish(seg)
        elif chosen.platform == "netease":
            seg = MessageSegment.music("163", int(chosen.song_id))
            await songcon_cmd.finish(seg)
        else:
            await songcon_cmd.finish(f"🎵 {chosen.title} - {chosen.artist}\n🔗 {chosen.share_url}")
    except FinishedException:
        raise  # 正常结束，不要捕获
    except Exception as e:
        logger.warning(f"音乐卡片发送失败: {e}")
        await songcon_cmd.finish(f"🎵 {chosen.title} - {chosen.artist}\n🔗 {chosen.share_url}")
