"""
AI 驱动的 RAG 知识图谱清理工具

使用 LLM 智能识别：
1. 重复实体（语义相似）
2. 无用节点（无意义或错误提取的实体）

使用方法：
    python tools/ai_cleanup_rag_graph.py              # 清理前10个用户
    python tools/ai_cleanup_rag_graph.py --user 123   # 清理指定用户
    python tools/ai_cleanup_rag_graph.py --all        # 清理所有用户（慎用，API调用多）
    python tools/ai_cleanup_rag_graph.py --limit 20   # 清理前20个用户
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import asyncio
from src.core.logger import setup_logger
from src.core.RAGM.graph_storage import GraphStorage
from src.core.RAGM.ai_graph_cleaner import AIGraphCleaner

logger = setup_logger(__name__)


def show_stats(graph_storage):
    """显示图谱统计信息"""
    stats = graph_storage.get_stats()
    
    print("\n" + "=" * 60)
    print("RAG 知识图谱统计信息")
    print("=" * 60)
    print(f"总节点数: {stats['total_nodes']}")
    print(f"总关系数: {stats['total_edges']}")
    print(f"用户数量: {stats['total_users']}")
    print(f"实体类型: {stats['entity_types']}")
    print("=" * 60 + "\n")


async def ai_cleanup_user(cleaner, user_id):
    """AI 清理指定用户"""
    print("\n" + "=" * 60)
    print(f"🤖 AI 清理用户: {user_id}")
    print("=" * 60)
    print()
    
    result = await cleaner.ai_cleanup_user(user_id)
    
    print()
    print("=" * 60)
    print(f"✅ 清理完成: 合并 {result['merged']} 个实体, 删除 {result['deleted']} 个无用实体")
    print("=" * 60 + "\n")


async def ai_cleanup_all(cleaner, limit):
    """AI 清理所有用户"""
    print("\n" + "=" * 60)
    print(f"🤖 AI 清理所有用户（最多 {limit} 个）")
    print("=" * 60)
    print()
    print("⚠️ 注意: 这将调用多次 AI API，可能需要较长时间")
    print()
    
    result = await cleaner.ai_cleanup_all_users(limit=limit)
    
    print()
    print("=" * 60)
    print(f"✅ 全局清理完成:")
    print(f"   处理用户: {result['users_processed']} 个")
    print(f"   合并实体: {result['total_merged']} 个")
    print(f"   删除实体: {result['total_deleted']} 个")
    print("=" * 60 + "\n")


async def main_async():
    parser = argparse.ArgumentParser(description="AI 驱动的 RAG 知识图谱清理工具")
    parser.add_argument("--user", type=str, help="指定用户 ID")
    parser.add_argument("--all", action="store_true", help="清理所有用户（慎用）")
    parser.add_argument("--limit", type=int, default=10, help="清理用户数量限制（默认10）")
    
    args = parser.parse_args()
    
    # 加载配置
    from src.core.config_manager import ConfigManager
    ConfigManager.load()
    
    # 初始化
    db_path = str(project_root / "data" / "knowledge_graph.db")
    graph_storage = GraphStorage(db_path=db_path)
    cleaner = AIGraphCleaner(graph_storage)
    
    # 显示清理前的统计信息
    print("\n【清理前】")
    show_stats(graph_storage)
    
    # 执行清理
    if args.user:
        # 清理指定用户
        await ai_cleanup_user(cleaner, args.user)
    elif args.all:
        # 清理所有用户
        users = graph_storage.get_users()
        await ai_cleanup_all(cleaner, limit=len(users))
    else:
        # 清理前 N 个用户
        await ai_cleanup_all(cleaner, limit=args.limit)
    
    # 显示清理后的统计信息
    print("\n【清理后】")
    show_stats(graph_storage)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ AI 清理失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
