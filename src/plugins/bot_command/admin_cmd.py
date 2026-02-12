"""
管理员命令处理器
提供系统自检、黑名单管理等管理功能
"""
import httpx
from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from src.core.config_manager import ConfigManager
from src.core.logger import logger
from src.core.temp_blacklist import get_temp_blacklist
from .utils import get_whitelist_info

logger.info("📝 加载管理员命令模块...")

# ============ 测试命令（验证命令是否能工作）============
test_simple = on_command("testsimple", permission=SUPERUSER, priority=1, block=True)

@test_simple.handle()
async def handle_test_simple():
    """最简单的测试命令"""
    await test_simple.finish("✅ 测试命令工作正常！")

# ============ /test 命令（仅超级用户）============
test_matcher = on_command("test", permission=SUPERUSER, priority=1, block=True)


@test_matcher.handle()
async def handle_test():
    """系统自检"""
    await test_matcher.send("🛠️ 开始系统自检...")
    
    report = []
    report.append("━━━━━━━━━━━━━━━━━━")
    report.append("🔍 系统自检报告")
    report.append("━━━━━━━━━━━━━━━━━━")
    
    # 1. 检查配置加载
    try:
        bot_config = ConfigManager.get_bot_config()
        ai_config = ConfigManager.get_ai_config()
        role_config = ConfigManager.get_role_config()
        
        report.append("\n📋 配置加载:")
        report.append(f"  ✅ Bot 配置: {bot_config.nickname}")
        report.append(f"  ✅ AI 配置: {ai_config.organizer.model_name}")
        report.append(f"  ✅ 角色配置: {role_config.persona.name}")
        
        # API Key 脱敏显示
        api_key = ai_config.common.api_key
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        report.append(f"  ✅ API Key: {masked_key}")
        
    except Exception as e:
        report.append(f"\n❌ 配置加载失败: {e}")
    
    # 2. 检查白名单
    try:
        whitelist_info = get_whitelist_info()
        report.append("\n🔐 白名单状态:")
        report.append(f"  启用: {'是' if whitelist_info.get('enabled') else '否'}")
        report.append(f"  允许所有私聊: {'是' if whitelist_info.get('allow_all_private') else '否'}")
        report.append(f"  白名单用户数: {whitelist_info.get('user_count', 0)}")
        report.append(f"  白名单群数: {whitelist_info.get('group_count', 0)}")
    except Exception as e:
        report.append(f"\n❌ 白名单检查失败: {e}")
    
    # 3. 检查 AI API 连接
    try:
        ai_config = ConfigManager.get_ai_config()
        # 获取默认供应商配置
        provider_name = ai_config.common.default_provider
        providers = getattr(ai_config, 'providers', {})
        if provider_name in providers:
            provider = providers[provider_name]
            api_base = provider.api_base
            api_key = provider.api_key
        elif hasattr(ai_config.common, 'api_base') and ai_config.common.api_base:
            api_base = ai_config.common.api_base
            api_key = ai_config.common.api_key
        else:
            raise ValueError(f"未找到供应商配置: {provider_name}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 尝试获取模型列表
            resp = await client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            
            if resp.status_code == 200:
                models_data = resp.json()
                model_count = len(models_data.get('data', []))
                report.append(f"\n🌐 AI API 连接:")
                report.append(f"  ✅ 状态: 正常")
                report.append(f"  ✅ 可用模型数: {model_count}")
            else:
                report.append(f"\n⚠️  AI API 连接:")
                report.append(f"  状态码: {resp.status_code}")
                report.append(f"  响应: {resp.text[:100]}")
                
    except Exception as e:
        report.append(f"\n❌ AI API 连接失败: {e}")
    
    # 4. 检查向量数据库
    try:
        from src.services.vector_service import get_vector_service
        vector_service = get_vector_service()
        
        # 获取记忆数量（使用正确的属性名）
        mem_count = vector_service.memory_collection.count()
        kb_count = vector_service.kb_collection.count()
        
        report.append(f"\n💾 向量数据库:")
        report.append(f"  ✅ 状态: 正常")
        report.append(f"  ✅ 对话记忆: {mem_count} 条")
        report.append(f"  ✅ 知识库: {kb_count} 条")
        
    except Exception as e:
        report.append(f"\n❌ 向量数据库异常: {e}")
        # 打印详细错误方便调试
        print(f"DEBUG DB Error: {e}")
    
    # 5. 检查表情包系统
    try:
        from src.services.emoji_service import get_emoji_service
        emoji_service = get_emoji_service()
        
        stats = emoji_service.get_stats()
        
        report.append(f"\n😊 表情包系统:")
        report.append(f"  ✅ 状态: 正常")
        report.append(f"  ✅ 表情数量: {stats.get('total', 0)}")
        report.append(f"  ✅ 存储大小: {stats.get('total_size_mb', 0):.2f} MB")
        report.append(f"  学习模式: {'开启' if stats.get('learning_enabled') else '关闭'}")
        report.append(f"  发送模式: {'开启' if stats.get('sending_enabled') else '关闭'}")
        
    except Exception as e:
        report.append(f"\n❌ 表情包系统异常: {e}")
    
    # 6. 检查黑名单系统
    try:
        from src.core.temp_blacklist import get_temp_blacklist
        blacklist = get_temp_blacklist()
        
        stats = blacklist.stats()
        
        report.append(f"\n🛡️ 黑名单系统:")
        report.append(f"  ✅ 状态: 正常")
        report.append(f"  ✅ 当前封禁: {stats.get('active_count', 0)} 人")
        report.append(f"  ✅ 今日新增: {stats.get('today_count', 0)} 人")
        
    except Exception as e:
        report.append(f"\n❌ 黑名单系统异常: {e}")
    
    report.append("\n━━━━━━━━━━━━━━━━━━")
    report.append("✅ 自检完成")
    
    await test_matcher.finish("\n".join(report))


# ============ 黑名单管理命令 ============

# /ban - 手动封禁用户
ban_matcher = on_command("ban", permission=SUPERUSER, priority=1, block=True)

@ban_matcher.handle()
async def handle_ban(event: MessageEvent, args: Message = CommandArg()):
    """手动封禁用户"""
    # 获取命令参数
    args_text = args.extract_plain_text().strip()
    
    logger.info(f"[DEBUG] ban 命令收到参数: '{args_text}'")
    
    if not args_text:
        await ban_matcher.finish("❌ 用法：/ban <用户ID> [分钟] [原因]\n示例：/ban 123456 60 违规行为")
    
    arg_list = args_text.split()
    
    if len(arg_list) < 1:
        await ban_matcher.finish("❌ 请指定用户ID")
    
    user_id = arg_list[0]
    minutes = 30  # 默认 30 分钟
    reason = "manual"
    
    # 解析分钟数和原因
    if len(arg_list) >= 2:
        try:
            # 尝试解析第二个参数为分钟数
            minutes = int(arg_list[1])
            if minutes <= 0 or minutes > 10080:  # 最大 7 天
                await ban_matcher.finish("❌ 封禁时长必须在 1-10080 分钟（7天）之间")
            
            # 如果有第三个及以后的参数，作为原因
            if len(arg_list) >= 3:
                reason = " ".join(arg_list[2:])
                
        except ValueError:
            # 如果第二个参数不是数字，将第二个及以后的参数都当作原因
            reason = " ".join(arg_list[1:])
            minutes = 30  # 使用默认时长
    
    logger.info(f"[DEBUG] 解析结果 - user_id: {user_id}, minutes: {minutes}, reason: {reason}")
    
    # 执行封禁
    blacklist = get_temp_blacklist()
    admin_id = str(event.user_id)
    result = blacklist.ban(user_id, minutes, reason, by=f"admin_{admin_id}")
    
    # 构建回复
    reply = [
        "✅ 封禁成功",
        f"━━━━━━━━━━━━━━━━━━",
        f"用户ID: {result['user_id']}",
        f"封禁时长: {result['remaining_minutes']} 分钟",
        f"原因: {result['reason']}",
        f"操作者: {result['blocked_by']}",
        f"命中次数: {result['hit_count']}"
    ]
    
    await ban_matcher.finish("\n".join(reply))


# /unban - 解除封禁
unban_matcher = on_command("unban", permission=SUPERUSER, priority=1, block=True)
logger.info("✅ 注册命令: /unban")

@unban_matcher.handle()
async def handle_unban(event: MessageEvent, args: Message = CommandArg()):
    """解除用户封禁"""
    # 获取命令参数
    args_text = args.extract_plain_text().strip()
    
    # 调试日志
    logger.info(f"[DEBUG] unban 命令收到参数: '{args_text}'")
    
    if not args_text:
        await unban_matcher.finish("❌ 用法：/unban <用户ID>\n示例：/unban 123456")
    
    arg_list = args_text.split()
    
    if len(arg_list) < 1:
        await unban_matcher.finish("❌ 请指定用户ID")
    
    user_id = arg_list[0]
    
    logger.info(f"[DEBUG] 解析后的 user_id: '{user_id}'")
    
    # 验证用户ID格式（应该是纯数字）
    if not user_id.isdigit():
        await unban_matcher.finish(f"❌ 用户ID格式错误: {user_id}")
    
    blacklist = get_temp_blacklist()
    success = blacklist.unban(user_id)
    
    if success:
        await unban_matcher.finish(f"✅ 用户 {user_id} 已解除封禁")
    else:
        await unban_matcher.finish(f"❌ 用户 {user_id} 不在黑名单中")


# /baninfo - 查询封禁信息# /baninfo - 查询封禁信息
baninfo_matcher = on_command("baninfo", permission=SUPERUSER, priority=1, block=True)

@baninfo_matcher.handle()
async def handle_baninfo(event: MessageEvent, args: Message = CommandArg()):
    """查询用户封禁信息"""
    args_text = args.extract_plain_text().strip()
    arg_list = args_text.split() if args_text else []
    
    # 如果没有参数，查询自己
    if len(arg_list) < 1:
        user_id = str(event.user_id)
    else:
        user_id = arg_list[0]
    
    blacklist = get_temp_blacklist()
    info = blacklist.get_info(user_id)
    
    if not info:
        await baninfo_matcher.finish(f"✅ 用户 {user_id} 未被封禁")
    
    # 格式化时间
    import time
    blocked_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info['blocked_at']))
    expires_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info['expires_at']))
    
    reply = [
        f"🚫 用户 {user_id} 封禁信息",
        f"━━━━━━━━━━━━━━━━━━",
        f"剩余时间: {info['remaining_minutes']} 分钟",
        f"原因: {info['reason']}",
        f"操作者: {info['blocked_by']}",
        f"命中次数: {info['hit_count']}",
        f"封禁时间: {blocked_time}",
        f"到期时间: {expires_time}"
    ]
    
    await baninfo_matcher.finish("\n".join(reply))
    
    if not info:
        await baninfo_matcher.finish(f"✅ 用户 {user_id} 未被封禁")
    
    # 格式化时间
    import time
    blocked_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info['blocked_at']))
    expires_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info['expires_at']))
    
    reply = [
        f"🚫 用户 {user_id} 封禁信息",
        f"━━━━━━━━━━━━━━━━━━",
        f"剩余时间: {info['remaining_minutes']} 分钟",
        f"原因: {info['reason']}",
        f"操作者: {info['blocked_by']}",
        f"命中次数: {info['hit_count']}",
        f"封禁时间: {blocked_time}",
        f"到期时间: {expires_time}"
    ]
    
    await baninfo_matcher.finish("\n".join(reply))


# /banlist - 查看黑名单列表
banlist_matcher = on_command("banlist", permission=SUPERUSER, priority=1, block=True)

@banlist_matcher.handle()
async def handle_banlist(event: MessageEvent, args: Message = CommandArg()):
    """查看当前黑名单列表"""
    args_text = args.extract_plain_text().strip()
    arg_list = args_text.split() if args_text else []
    
    page = 1
    page_size = 10
    
    # 解析页码
    if len(arg_list) >= 1:
        try:
            page = int(arg_list[0])
            if page < 1:
                page = 1
        except ValueError:
            pass
    
    # 解析每页条数
    if len(arg_list) >= 2:
        try:
            page_size = int(arg_list[1])
            if page_size < 1 or page_size > 50:
                page_size = 10
        except ValueError:
            pass
    
    blacklist = get_temp_blacklist()
    result = blacklist.list_active(page, page_size)
    
    if result['total'] == 0:
        await banlist_matcher.finish("✅ 当前黑名单为空")
    
    reply = [
        f"🚫 黑名单列表（第 {result['page']}/{result['total_pages']} 页）",
        f"━━━━━━━━━━━━━━━━━━",
        f"总计: {result['total']} 人"
    ]
    
    for i, record in enumerate(result['records'], 1):
        reply.append(f"\n{i}. 用户 {record['user_id']}")
        reply.append(f"   剩余: {record['remaining_minutes']} 分钟")
        reply.append(f"   原因: {record['reason']}")
        reply.append(f"   命中: {record['hit_count']} 次")
    
    reply.append(f"\n━━━━━━━━━━━━━━━━━━")
    reply.append(f"提示：/banlist [页码] [每页条数]")
    
    await banlist_matcher.finish("\n".join(reply))


# /banstat - 黑名单统计
banstat_matcher = on_command("banstat", permission=SUPERUSER, priority=1, block=True)

@banstat_matcher.handle()
async def handle_banstat():
    """查看黑名单统计信息"""
    blacklist = get_temp_blacklist()
    stats = blacklist.stats()
    
    reply = [
        "📊 黑名单统计",
        "━━━━━━━━━━━━━━━━━━",
        f"当前活跃封禁: {stats['active_count']} 人",
        f"今日新增封禁: {stats['today_count']} 人"
    ]
    
    if stats['top_reasons']:
        reply.append("\n最常见原因:")
        for i, item in enumerate(stats['top_reasons'], 1):
            reply.append(f"  {i}. {item['reason']}: {item['count']} 次")
    
    if stats['top_offenders']:
        reply.append("\n命中次数 Top 5:")
        for i, item in enumerate(stats['top_offenders'], 1):
            reply.append(f"  {i}. 用户 {item['user_id']}: {item['hit_count']} 次")
    
    await banstat_matcher.finish("\n".join(reply))


# /banclean - 清理过期记录
banclean_matcher = on_command("banclean", permission=SUPERUSER, priority=1, block=True)

@banclean_matcher.handle()
async def handle_banclean():
    """手动清理过期黑名单记录"""
    blacklist = get_temp_blacklist()
    deleted = blacklist.cleanup_expired()
    
    await banclean_matcher.finish(f"🧹 清理完成，删除了 {deleted} 条过期记录")
