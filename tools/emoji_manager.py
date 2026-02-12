"""
表情包管理工具
用于查看、搜索和删除表情包

使用方法：
    python tools/emoji_manager.py list              # 列出所有表情包
    python tools/emoji_manager.py search "灰色兔子"  # 搜索表情包
    python tools/emoji_manager.py delete <hash>     # 删除指定表情包
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载配置
from src.core.config_manager import ConfigManager
ConfigManager.load()

import chromadb
from src.services.vector_service import SiliconFlowEmbedding


def get_emoji_collection():
    """获取表情包集合"""
    bot_config = ConfigManager.get_bot_config()
    db_path = bot_config.storage.vector_db_path
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name="emoji_library",
        embedding_function=SiliconFlowEmbedding(),
        metadata={"hnsw:space": "cosine"}
    )


def list_all():
    """列出所有表情包"""
    collection = get_emoji_collection()
    results = collection.get()
    
    ids = results.get('ids', [])
    docs = results.get('documents', [])
    metas = results.get('metadatas', [])
    
    if not ids:
        print("📭 表情库为空")
        return
    
    print(f"📦 共 {len(ids)} 个表情包:\n")
    print("-" * 80)
    
    for i, (hash_id, desc, meta) in enumerate(zip(ids, docs, metas), 1):
        file_path = meta.get('path', 'N/A')
        exists = "✅" if Path(file_path).exists() else "❌"
        print(f"{i:3}. [{hash_id[:8]}...] {exists} {desc}")
    
    print("-" * 80)


def search(query: str, top_k: int = 5):
    """搜索表情包"""
    collection = get_emoji_collection()
    
    results = collection.query(
        query_texts=[query],
        n_results=top_k
    )
    
    ids = results.get('ids', [[]])[0]
    docs = results.get('documents', [[]])[0]
    metas = results.get('metadatas', [[]])[0]
    distances = results.get('distances', [[]])[0]
    
    if not ids:
        print(f"🔍 未找到与 '{query}' 相关的表情包")
        return
    
    print(f"🔍 搜索 '{query}' 的结果:\n")
    print("-" * 80)
    
    for i, (hash_id, desc, meta, dist) in enumerate(zip(ids, docs, metas, distances), 1):
        similarity = 1 - dist
        file_path = meta.get('path', 'N/A')
        exists = "✅" if Path(file_path).exists() else "❌"
        
        print(f"{i}. 相似度: {similarity:.2%}")
        print(f"   哈希: {hash_id}")
        print(f"   描述: {desc}")
        print(f"   文件: {exists} {file_path}")
        print()
    
    print("-" * 80)
    print("💡 使用 'python tools/emoji_manager.py delete <完整哈希>' 删除表情包")


def delete(hash_id: str):
    """删除表情包"""
    collection = get_emoji_collection()
    
    # 先查询确认存在
    existing = collection.get(ids=[hash_id])
    
    if not existing['ids']:
        # 尝试模糊匹配
        all_results = collection.get()
        matches = [id for id in all_results.get('ids', []) if id.startswith(hash_id)]
        
        if len(matches) == 1:
            hash_id = matches[0]
            existing = collection.get(ids=[hash_id])
        elif len(matches) > 1:
            print(f"⚠️  找到多个匹配的哈希值:")
            for m in matches:
                print(f"   - {m}")
            print("请提供更完整的哈希值")
            return
        else:
            print(f"❌ 未找到哈希为 '{hash_id}' 的表情包")
            return
    
    # 显示要删除的内容
    desc = existing['documents'][0]
    meta = existing['metadatas'][0]
    file_path = Path(meta.get('path', ''))
    
    print(f"🗑️  即将删除:")
    print(f"   哈希: {hash_id}")
    print(f"   描述: {desc}")
    print(f"   文件: {file_path}")
    
    confirm = input("\n确认删除? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ 已取消")
        return
    
    # 从向量数据库删除
    collection.delete(ids=[hash_id])
    print("✅ 已从向量数据库删除")
    
    # 删除文件
    if file_path.exists():
        file_path.unlink()
        print(f"✅ 已删除文件: {file_path}")
    else:
        print(f"⚠️  文件不存在: {file_path}")
    
    print("🎉 删除完成!")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_all()
    elif command == "search":
        if len(sys.argv) < 3:
            print("用法: python tools/emoji_manager.py search <关键词>")
            return
        query = " ".join(sys.argv[2:])
        search(query)
    elif command == "delete":
        if len(sys.argv) < 3:
            print("用法: python tools/emoji_manager.py delete <哈希值>")
            return
        hash_id = sys.argv[2]
        delete(hash_id)
    else:
        print(f"未知命令: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
