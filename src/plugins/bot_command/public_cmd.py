"""
公共命令处理器
提供帮助、白名单申请等功能
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.params import CommandArg
from src.core.logger import logger
from .utils import add_whitelist

# ============ /help 命令 ============
help_matcher = on_command("help", priority=5, block=True)


@help_matcher.handle()
async def handle_help():
    """显示帮助信息"""
    msg = (
        "月代雪 Bot 命令列表\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "聊天方式:\n"
        "  @我 <消息> - 在群里@我聊天\n"
        "  /chat <消息> - 使用命令聊天\n"
        "\n"
        "公共命令:\n"
        "  /help - 显示此帮助信息\n"
        "  /openbot [群号] - 申请开通群权限\n"
        "  /openfrd - 申请开通私聊权限\n"
        "  /status - 查看机器人状态\n"
        "  /好感度 - 查看与 Yuki 的好感度\n"
        "\n"
        "点歌功能:\n"
        "  /song <歌名> - 搜索歌曲\n"
        "  /songcon <序号> - 选择并发送音乐卡片\n"
        "\n"
        "管理命令 (仅超级用户):\n"
        "  /test - 系统自检\n"
        "  /clear - 清除对话记忆\n"
        "  /config - 查看配置\n"
        "  /reload - 重载配置\n"
        "\n"
        "黑名单管理 (仅超级用户):\n"
        "  /ban <用户ID> [分钟] [原因] - 封禁用户\n"
        "  /unban <用户ID> - 解除封禁\n"
        "  /baninfo [用户ID] - 查询封禁信息\n"
        "  /banlist [页码] - 查看黑名单列表\n"
        "  /banstat - 查看黑名单统计\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "直接@我就能聊天哦~"
    )
    await help_matcher.finish(msg)


# ============ /openbot 命令（统一处理私聊和群聊）============
open_group = on_command("openbot", priority=5, block=True)


@open_group.handle()
async def handle_open_group(event: MessageEvent, args: Message = CommandArg()):
    """
    开通群权限
    - 群聊：直接激活当前群
    - 私聊：需要跟群号，例如 /openbot 123456789
    """
    # 群聊模式：直接激活当前群
    if isinstance(event, GroupMessageEvent):
        gid = event.group_id
        user_id = event.user_id
        
        logger.info(f"📝 用户 {user_id} 在群 {gid} 中申请开通")
        
        if add_whitelist(gid, 'group'):
            await open_group.finish(
                f"✅ 激活成功！\n"
                f"本群 [{gid}] 已加入白名单\n"
                f"大家可以愉快地使用 Bot 了~"
            )
        else:
            await open_group.finish("❌ 激活失败，请联系管理员")
    
    # 私聊模式：需要跟群号
    else:
        group_id_str = args.extract_plain_text().strip()
        
        if not group_id_str:
            await open_group.finish(
                "请在指令后加上群号，例如：\n"
                "/openbot 123456789\n"
                "\n"
                "或者在群里直接发送 /openbot"
            )
        
        if not group_id_str.isdigit():
            await open_group.finish("❌ 群号必须是纯数字")
        
        gid = int(group_id_str)
        
        logger.info(f"📝 用户 {event.user_id} 申请开通群 {gid}")
        
        if add_whitelist(gid, 'group'):
            await open_group.finish(
                f"✅ 成功！\n"
                f"群 [{gid}] 已加入白名单\n"
                f"现在可以在该群使用 Bot 了~"
            )
        else:
            await open_group.finish("❌ 配置写入失败，请联系管理员")


# ============ /openfrd 命令（私聊和群聊都可用）============
open_friend = on_command("openfrd", priority=5, block=True)


@open_friend.handle()
async def handle_open_friend(event: PrivateMessageEvent | GroupMessageEvent):
    """
    申请私聊权限
    例如：/openfrd 或 /openfrd 123456789
    """
    uid = event.user_id
    
    logger.info(f"📝 用户 {uid} 申请私聊权限")
    
    if add_whitelist(uid, 'user'):
        await open_friend.finish(
            f"✅ 申请成功！\n"
            f"你 ({uid}) 已获得私聊权限\n"
            f"现在可以直接私聊和我聊天了~"
        )
    else:
        await open_friend.finish("❌ 申请失败，请联系管理员")
