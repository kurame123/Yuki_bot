import re

from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment

from . import config

repeater_group = config.repeater_group
shortest = config.shortest_length
blacklist = config.blacklist

m = on_message(priority=10, block=False)

last_message = {}
message_times = {}


# 消息预处理 - 生成用于比较的标准化消息
def message_preprocess(message: str):
    raw_message = message
    contained_images = {}
    images = re.findall(r'\[CQ:image.*?]', message)
    pattern = r'file=http://gchat.qpic.cn/gchatpic_new/\d+/\d+-\d+-(.*?)/.*?[,\]]'
    for i in images:
        url_match = re.findall(r'url=(.*?)[,\]]', i)
        hash_match = re.findall(pattern, i)
        if url_match and hash_match:
            contained_images.update({i: [url_match[0], hash_match[0]]})
        elif hash_match:
            contained_images.update({i: ['', hash_match[0]]})
    for i in contained_images:
        message = message.replace(i, f'[{contained_images[i][1]}]')
    return message, raw_message


def build_safe_message(event: GroupMessageEvent) -> Message:
    """
    构建安全的消息对象，避免风控
    对于图片，使用 file 参数而非直接使用原始 CQ 码
    """
    safe_msg = Message()
    for seg in event.message:
        if seg.type == "image":
            # 优先使用 file 字段（通常是本地缓存或安全的标识符）
            # 如果没有 file，则使用 url
            file = seg.data.get("file") or seg.data.get("url")
            if file:
                safe_msg.append(MessageSegment.image(file))
        elif seg.type == "face":
            # QQ 表情直接复制
            safe_msg.append(seg)
        elif seg.type == "text":
            text = seg.data.get("text", "")
            if text:
                safe_msg.append(MessageSegment.text(text))
        else:
            # 其他类型直接复制
            safe_msg.append(seg)
    return safe_msg


@m.handle()
async def repeater(bot: Bot, event: GroupMessageEvent):
    # 检查是否在黑名单中
    if event.raw_message in blacklist:
        logger.debug(f'[复读姬] 检测到黑名单消息: {event.raw_message}')
        return
    gid = str(event.group_id)
    if gid in repeater_group or "all" in repeater_group:
        global last_message, message_times
        message, raw_message = message_preprocess(str(event.message))
        logger.debug(f'[复读姬] 这一次消息: {message}')
        logger.debug(f'[复读姬] 上一次消息: {last_message.get(gid)}')
        if last_message.get(gid) != message:
            message_times[gid] = 1
        else:
            message_times[gid] += 1
        logger.debug(f'[复读姬] 已重复次数: {message_times.get(gid)}/{config.shortest_times}')
        if message_times.get(gid) == config.shortest_times:
            logger.debug(f'[复读姬] 原始的消息: {str(event.message)}')
            # 使用安全的消息构建方式，避免风控
            safe_message = build_safe_message(event)
            logger.debug(f"[复读姬] 欲发送信息: {safe_message}")
            await bot.send_group_msg(group_id=event.group_id, message=safe_message)
        last_message[gid] = message
