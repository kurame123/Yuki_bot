"""
ChromaDB 迁移到 FAISS + SQLite
将现有的 ChromaDB 数据迁移到新的 FAISS 架构
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import sqlite3
import numpy as np
import faiss

try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    print("⚠️  未安装 chromadb")
    print("   如需迁移旧数据，请先安装: pip install chromadb")
    print("   或者直接使用新系统（旧数据会保留但不会被使用）")
    response = input("\n是否继续？(Y/N): ").strip().upper()
    if response != 'Y':
        sys.exit(0)

from src.core.config_manager import ConfigManager
from src.services.vector_service import EmbeddingClient


def migrate():
    """执行迁移"""
    if not HAS_CHROMADB:
        print("\n❌ 无法执行迁移：未安装 chromadb")
        print("   请先安装: pip install chromadb")
        return
    
    print("=" * 60)
    print("ChromaDB → FAISS + SQLite 数据迁移工具")
    print("=" * 60)
    
    # 加载配置
    ConfigManager.load()
    bot_config = ConfigManager.get_bot_config()
    ai_config = ConfigManager.get_ai_config()
    
    db_path = Path(bot_config.storage.vector_db_path)
    vector_dim = ai_config.embedding.vector_dim
    
    # 检查旧数据库
    chroma_path = db_path / "chroma.sqlite3"
    if not chroma_path.exists():
        print("✅ 未发现 ChromaDB 数据，无需迁移")
        return
    
    print(f"\n📂 发现 ChromaDB 数据: {chroma_path}")
    print("开始迁移...")
    
    try:
        # 连接 ChromaDB
        client = chromadb.PersistentClient(path=str(db_path))
        
        # 迁移记忆集合
        print("\n1️⃣ 迁移对话记忆...")
        try:
            memory_collection = client.get_collection("chat_memory")
            migrate_memory_collection(memory_collection, db_path, vector_dim)
        except Exception as e:
            print(f"   ⚠️ 记忆集合迁移失败: {e}")
        
        # 迁移知识库集合
        print("\n2️⃣ 迁移知识库...")
        try:
            kb_collection = client.get_collection("knowledge_base")
            migrate_kb_collection(kb_collection, db_path, vector_dim)
        except Exception as e:
            print(f"   ⚠️ 知识库迁移失败: {e}")
        
        print("\n" + "=" * 60)
        print("✅ 迁移完成！")
        print("=" * 60)
        print("\n提示：")
        print("1. 旧数据已保留在原位置")
        print("2. 新数据位于:")
        print(f"   - {db_path / 'memory.db'}")
        print(f"   - {db_path / 'memory.faiss'}")
        print(f"   - {db_path / 'knowledge.db'}")
        print(f"   - {db_path / 'knowledge.faiss'}")
        print("3. 确认无误后可删除旧的 ChromaDB 数据")
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()


def migrate_memory_collection(collection, db_path: Path, vector_dim: int):
    """迁移记忆集合"""
    import pickle
    
    # 获取所有数据
    results = collection.get(include=["embeddings", "metadatas", "documents"])
    
    ids = results.get('ids', [])
    embeddings = results.get('embeddings', [])
    metadatas = results.get('metadatas', [])
    documents = results.get('documents', [])
    
    if not ids:
        print("   ⏭️ 记忆集合为空，跳过")
        return
    
    print(f"   📊 找到 {len(ids)} 条记忆")
    
    # 创建 SQLite 数据库
    memory_db_path = db_path / "memory.db"
    conn = sqlite3.connect(str(memory_db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            query TEXT,
            reply TEXT,
            memory_type TEXT
        )
    """)
    
    # 创建 FAISS 索引和 ID 映射
    index = faiss.IndexFlatIP(vector_dim)
    id_map = []  # FAISS index -> SQLite id
    
    # 迁移数据
    for i, (doc, meta, emb) in enumerate(zip(documents, metadatas, embeddings)):
        user_id = meta.get('user_id', 'unknown')
        role = meta.get('role', 'Unknown')
        timestamp = meta.get('timestamp', 0)
        query = meta.get('query')
        reply = meta.get('reply')
        memory_type = meta.get('memory_type')
        
        # 插入 SQLite
        cursor.execute("""
            INSERT INTO memories (user_id, role, content, timestamp, query, reply, memory_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, role, doc, timestamp, query, reply, memory_type))
        
        memory_id = cursor.lastrowid
        
        # 添加到 FAISS
        vec = np.array(emb, dtype=np.float32).reshape(1, -1)
        # 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        index.add(vec)
        
        # 记录 ID 映射
        id_map.append(memory_id)
        
        if (i + 1) % 100 == 0:
            print(f"   进度: {i + 1}/{len(ids)}")
    
    conn.commit()
    conn.close()
    
    # 保存 FAISS 索引
    memory_index_path = db_path / "memory.faiss"
    faiss.write_index(index, str(memory_index_path))
    
    # 保存 ID 映射
    id_map_path = db_path / "memory_id_map.pkl"
    with open(id_map_path, 'wb') as f:
        pickle.dump(id_map, f)
    
    print(f"   ✅ 记忆迁移完成: {len(ids)} 条")


def migrate_kb_collection(collection, db_path: Path, vector_dim: int):
    """迁移知识库集合"""
    import pickle
    
    # 获取所有数据
    results = collection.get(include=["embeddings", "metadatas", "documents"])
    
    ids = results.get('ids', [])
    embeddings = results.get('embeddings', [])
    metadatas = results.get('metadatas', [])
    documents = results.get('documents', [])
    
    if not ids:
        print("   ⏭️ 知识库为空，跳过")
        return
    
    print(f"   📊 找到 {len(ids)} 条知识")
    
    # 创建 SQLite 数据库
    kb_db_path = db_path / "knowledge.db"
    conn = sqlite3.connect(str(kb_db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            title TEXT,
            category TEXT
        )
    """)
    
    # 创建 FAISS 索引和 ID 映射
    index = faiss.IndexFlatIP(vector_dim)
    id_map = []  # FAISS index -> SQLite id
    
    # 迁移数据
    for i, (doc, meta, emb) in enumerate(zip(documents, metadatas, embeddings)):
        source = meta.get('source', 'Unknown')
        title = meta.get('title')
        category = meta.get('category')
        
        # 插入 SQLite
        cursor.execute("""
            INSERT INTO knowledge (source, content, title, category)
            VALUES (?, ?, ?, ?)
        """, (source, doc, title, category))
        
        kb_id = cursor.lastrowid
        
        # 添加到 FAISS
        vec = np.array(emb, dtype=np.float32).reshape(1, -1)
        # 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        index.add(vec)
        
        # 记录 ID 映射
        id_map.append(kb_id)
        
        if (i + 1) % 100 == 0:
            print(f"   进度: {i + 1}/{len(ids)}")
    
    conn.commit()
    conn.close()
    
    # 保存 FAISS 索引
    kb_index_path = db_path / "knowledge.faiss"
    faiss.write_index(index, str(kb_index_path))
    
    # 保存 ID 映射
    id_map_path = db_path / "kb_id_map.pkl"
    with open(id_map_path, 'wb') as f:
        pickle.dump(id_map, f)
    
    print(f"   ✅ 知识库迁移完成: {len(ids)} 条")


if __name__ == "__main__":
    migrate()
