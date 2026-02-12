"""
FAISS + SQLite 向量服务（双数据库架构）
- 私聊数据库：一个用户一个数据库，包含私聊和群聊记忆
- 群聊数据库：一个群一个数据库，包含所有成员的发言
- FAISS: 高性能向量检索，支持跨群组检索
"""
import os
import time
import sqlite3
import pickle
import httpx
import numpy as np
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass

try:
    import faiss
except ImportError:
    raise ImportError("请安装 faiss: pip install faiss-cpu")

from src.core.config_manager import ConfigManager
from src.core.logger import logger


@dataclass
class MemoryMetadata:
    """记忆元数据"""
    id: int
    user_id: str
    role: str
    content: str
    timestamp: int
    query: Optional[str] = None
    reply: Optional[str] = None
    memory_type: Optional[str] = None


@dataclass
class KnowledgeMetadata:
    """知识库元数据"""
    id: int
    source: str
    content: str
    title: Optional[str] = None
    category: Optional[str] = None


class EmbeddingClient:
    """嵌入向量生成客户端"""
    
    def __init__(self):
        ai_config = ConfigManager.get_ai_config()
        embedding_config = ai_config.embedding
        provider_name = getattr(embedding_config, 'provider', '') or ai_config.common.default_provider
        
        providers = getattr(ai_config, 'providers', {})
        if provider_name in providers:
            provider = providers[provider_name]
            self.base_url = provider.api_base
            self.api_key = provider.api_key
            self.timeout = provider.timeout
        else:
            raise ValueError(f"未找到供应商配置: {provider_name}")
        
        self.model = embedding_config.model_name
        self.vector_dim = embedding_config.vector_dim
        
        logger.info(f"🧠 嵌入客户端初始化: {self.model}")
    
    def get_embedding(self, text: str) -> np.ndarray:
        """生成文本的嵌入向量"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": text,
            "encoding_format": "float"
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=headers
                )
                resp.raise_for_status()
                result = resp.json()
                
                if 'data' in result and len(result['data']) > 0:
                    embedding = result['data'][0]['embedding']
                    return np.array(embedding, dtype=np.float32)
                else:
                    logger.error(f"❌ API 返回异常: {result}")
                    return np.zeros(self.vector_dim, dtype=np.float32)
        
        except Exception as e:
            logger.error(f"❌ 生成嵌入失败: {e}")
            return np.zeros(self.vector_dim, dtype=np.float32)


class FAISSVectorService:
    """FAISS + SQLite 向量服务（双数据库架构）"""
    
    def __init__(self):
        bot_config = ConfigManager.get_bot_config()
        ai_config = ConfigManager.get_ai_config()
        
        # 配置参数
        self.db_path = Path(bot_config.storage.vector_db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self._load_config()
        
        self.vector_dim = ai_config.embedding.vector_dim
        
        # 初始化嵌入客户端
        self.embedding_client = EmbeddingClient()
        
        # 双数据库架构
        self.private_db_dir = self.db_path / "private"  # 私聊数据库目录
        self.group_db_dir = self.db_path / "groups"     # 群聊数据库目录
        self.private_db_dir.mkdir(parents=True, exist_ok=True)
        self.group_db_dir.mkdir(parents=True, exist_ok=True)
        
        # 知识库数据库（保持不变）
        self.kb_db_path = self.db_path / "knowledge.db"
        
        # 初始化数据库和索引
        self._init_sqlite()
        self._init_faiss()
        
        # 缓存已加载的数据库连接和索引
        self._private_dbs = {}  # {user_id: connection}
        self._group_dbs = {}    # {group_id: connection}
        self._private_indices = {}  # {user_id: (index, id_map)}
        self._group_indices = {}    # {group_id: (index, id_map)}
        
        # 初始化检索统计
        self._last_kb_search_stats = {}
        
        logger.info(f"✅ FAISS 向量服务初始化成功（双数据库架构）")
        logger.info(f"   - 私聊数据库目录: {self.private_db_dir}")
        logger.info(f"   - 群聊数据库目录: {self.group_db_dir}")
        logger.info(f"   - 知识库: {self.kb_db_path}")
        logger.info(f"   - 向量维度: {self.vector_dim}")
    
    def _load_config(self):
        """加载配置参数"""
        bot_config = ConfigManager.get_bot_config()
        
        self.retrieve_count = bot_config.storage.retrieve_count
        self.similarity_threshold = bot_config.storage.similarity_threshold
        self.min_memory_length = bot_config.storage.min_memory_length
        self.max_memory_per_user = bot_config.storage.max_memory_per_user
        self.enabled = bot_config.storage.enable_vector_memory
        
        logger.debug(f"配置已加载: 阈值={self.similarity_threshold}, 检索数={self.retrieve_count}")
    
    def reload_config(self):
        """热重载配置（不重启服务）"""
        old_threshold = self.similarity_threshold
        self._load_config()
        logger.info(f"🔄 配置已重载: 阈值 {old_threshold} → {self.similarity_threshold}")
    
    def _init_sqlite(self):
        """初始化 SQLite 数据库（双数据库架构）"""
        # 知识库数据库（保持不变）
        conn = sqlite3.connect(str(self.kb_db_path))
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON knowledge(source)")
        conn.commit()
        conn.close()
        
        logger.info("✅ 知识库数据库初始化完成")
        logger.info("   私聊和群聊数据库将按需创建")
    
    def _get_private_db_path(self, user_id: str) -> Path:
        """获取用户私聊数据库路径"""
        return self.private_db_dir / f"user_{user_id}.db"
    
    def _get_group_db_path(self, group_id: str) -> Path:
        """获取群聊数据库路径"""
        return self.group_db_dir / f"group_{group_id}.db"
    
    def _init_private_db(self, user_id: str):
        """初始化用户私聊数据库（一个用户一个数据库）"""
        db_path = self._get_private_db_path(user_id)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 私聊数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS private_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                query TEXT,
                reply TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON private_memories(timestamp)")
        
        # 群聊数据表（该用户在各个群的发言）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                query TEXT,
                reply TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_timestamp ON group_memories(group_id, timestamp)")
        
        conn.commit()
        conn.close()
        logger.debug(f"✅ 初始化用户 {user_id} 的私聊数据库")
    
    def _init_group_db(self, group_id: str):
        """初始化群聊数据库（一个群一个数据库）"""
        db_path = self._get_group_db_path(group_id)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 群成员记忆表（每个用户的发言）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS member_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                sender_name TEXT,
                query TEXT,
                reply TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_timestamp ON member_memories(user_id, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON member_memories(timestamp)")
        
        conn.commit()
        conn.close()
        logger.debug(f"✅ 初始化群 {group_id} 的群聊数据库")
    
    def _init_faiss(self):
        """初始化 FAISS 索引（双数据库架构）"""
        # 知识库索引（保持不变）
        kb_index_path = self.db_path / "knowledge.faiss"
        kb_id_map_path = self.db_path / "kb_id_map.pkl"
        
        if kb_index_path.exists():
            self.kb_index = faiss.read_index(str(kb_index_path))
            if kb_id_map_path.exists():
                with open(kb_id_map_path, 'rb') as f:
                    self.kb_id_map = pickle.load(f)
            else:
                self.kb_id_map = []
            logger.info(f"   - 加载知识库索引: {self.kb_index.ntotal} 条")
        else:
            self.kb_index = faiss.IndexFlatIP(self.vector_dim)
            self.kb_id_map = []
            logger.info(f"   - 创建新知识库索引")
        
        logger.info("   - 私聊和群聊索引将按需加载")
    
    def _get_private_index_path(self, user_id: str) -> Tuple[Path, Path]:
        """获取用户私聊索引路径"""
        index_path = self.private_db_dir / f"user_{user_id}.faiss"
        id_map_path = self.private_db_dir / f"user_{user_id}_id_map.pkl"
        return index_path, id_map_path
    
    def _get_group_index_path(self, group_id: str) -> Tuple[Path, Path]:
        """获取群聊索引路径"""
        index_path = self.group_db_dir / f"group_{group_id}.faiss"
        id_map_path = self.group_db_dir / f"group_{group_id}_id_map.pkl"
        return index_path, id_map_path
    
    def _load_private_index(self, user_id: str) -> Tuple:
        """加载用户私聊索引"""
        if user_id in self._private_indices:
            return self._private_indices[user_id]
        
        index_path, id_map_path = self._get_private_index_path(user_id)
        
        if index_path.exists():
            index = faiss.read_index(str(index_path))
            if id_map_path.exists():
                with open(id_map_path, 'rb') as f:
                    id_map = pickle.load(f)
            else:
                id_map = []
        else:
            index = faiss.IndexFlatIP(self.vector_dim)
            id_map = []
        
        self._private_indices[user_id] = (index, id_map)
        return index, id_map
    
    def _load_group_index(self, group_id: str) -> Tuple:
        """加载群聊索引"""
        if group_id in self._group_indices:
            return self._group_indices[group_id]
        
        index_path, id_map_path = self._get_group_index_path(group_id)
        
        if index_path.exists():
            index = faiss.read_index(str(index_path))
            if id_map_path.exists():
                with open(id_map_path, 'rb') as f:
                    id_map = pickle.load(f)
            else:
                id_map = []
        else:
            index = faiss.IndexFlatIP(self.vector_dim)
            id_map = []
        
        self._group_indices[group_id] = (index, id_map)
        return index, id_map
    
    def _save_private_index(self, user_id: str):
        """保存用户私聊索引"""
        if user_id not in self._private_indices:
            return
        
        index, id_map = self._private_indices[user_id]
        index_path, id_map_path = self._get_private_index_path(user_id)
        
        faiss.write_index(index, str(index_path))
        with open(id_map_path, 'wb') as f:
            pickle.dump(id_map, f)
    
    def _save_group_index(self, group_id: str):
        """保存群聊索引"""
        if group_id not in self._group_indices:
            return
        
        index, id_map = self._group_indices[group_id]
        index_path, id_map_path = self._get_group_index_path(group_id)
        
        faiss.write_index(index, str(index_path))
        with open(id_map_path, 'wb') as f:
            pickle.dump(id_map, f)
    
    def _save_faiss_index(self, index_type: str):
        """保存 FAISS 索引和 ID 映射到磁盘"""
        if index_type == "knowledge":
            kb_index_path = self.db_path / "knowledge.faiss"
            kb_id_map_path = self.db_path / "kb_id_map.pkl"
            faiss.write_index(self.kb_index, str(kb_index_path))
            with open(kb_id_map_path, 'wb') as f:
                pickle.dump(self.kb_id_map, f)
        else:
            logger.warning(f"未知的索引类型: {index_type}，使用新的保存方法")
    
    def _normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        """归一化向量（用于内积相似度）"""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec
    
    def add_memory(self, user_id: str, text: str, role: str) -> bool:
        """
        添加单条记忆（已废弃，请使用 add_pair_memory）
        保留此方法以兼容旧代码
        """
        logger.warning("add_memory 方法已废弃，请使用 add_pair_memory")
        return False
    
    def add_pair_memory(
        self, 
        user_id: str, 
        query: str, 
        reply: str,
        group_id: str = None,
        sender_name: str = None
    ) -> bool:
        """
        添加 Q&A 对记忆（双数据库架构）
        
        Args:
            user_id: 用户ID
            query: 用户问题
            reply: Bot回复
            group_id: 群ID（如果是群聊）
            sender_name: 发送者昵称（群聊时使用）
        """
        if not self.enabled:
            return False
        
        combined_text = f"User问: {query}\nBot答: {reply}"
        
        try:
            # 生成向量
            embedding = self.embedding_client.get_embedding(combined_text)
            embedding = self._normalize_vector(embedding)
            
            if group_id:
                # 群聊记忆：存储到两个地方
                # 1. 用户的私聊数据库（group_memories 表）
                self._add_to_user_group_memory(user_id, group_id, query, reply, combined_text, embedding)
                
                # 2. 群的数据库（member_memories 表）
                self._add_to_group_member_memory(group_id, user_id, query, reply, combined_text, embedding, sender_name)
            else:
                # 私聊记忆：只存储到用户的私聊数据库（private_memories 表）
                self._add_to_user_private_memory(user_id, query, reply, combined_text, embedding)
            
            logger.debug(f"💾 记忆已存储: user={user_id}, group={group_id}, query={query[:30]}")
            return True
        
        except Exception as e:
            logger.error(f"❌ 存储记忆失败: {e}")
            return False
    
    def _add_to_user_private_memory(self, user_id: str, query: str, reply: str, combined_text: str, embedding: np.ndarray):
        """添加到用户的私聊记忆"""
        # 初始化数据库（如果不存在）
        db_path = self._get_private_db_path(user_id)
        if not db_path.exists():
            self._init_private_db(user_id)
        
        # 存储元数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO private_memories (role, content, timestamp, query, reply)
            VALUES (?, ?, ?, ?, ?)
        """, ("Pair", combined_text, int(time.time()), query, reply))
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 添加向量到 FAISS
        index, id_map = self._load_private_index(user_id)
        index.add(embedding.reshape(1, -1))
        id_map.append(memory_id)
        self._private_indices[user_id] = (index, id_map)
        self._save_private_index(user_id)
    
    def _add_to_user_group_memory(self, user_id: str, group_id: str, query: str, reply: str, combined_text: str, embedding: np.ndarray):
        """添加到用户的群聊记忆（用户视角）"""
        # 初始化数据库（如果不存在）
        db_path = self._get_private_db_path(user_id)
        if not db_path.exists():
            self._init_private_db(user_id)
        
        # 存储元数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO group_memories (group_id, role, content, timestamp, query, reply)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (group_id, "Pair", combined_text, int(time.time()), query, reply))
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 添加向量到用户的私聊索引（包含群聊记忆）
        index, id_map = self._load_private_index(user_id)
        index.add(embedding.reshape(1, -1))
        id_map.append(('group', memory_id))  # 标记为群聊记忆
        self._private_indices[user_id] = (index, id_map)
        self._save_private_index(user_id)
    
    def _add_to_group_member_memory(self, group_id: str, user_id: str, query: str, reply: str, combined_text: str, embedding: np.ndarray, sender_name: str = None):
        """添加到群的成员记忆（群视角）"""
        # 初始化数据库（如果不存在）
        db_path = self._get_group_db_path(group_id)
        if not db_path.exists():
            self._init_group_db(group_id)
        
        # 存储元数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO member_memories (user_id, role, content, timestamp, sender_name, query, reply)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "Pair", combined_text, int(time.time()), sender_name, query, reply))
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 添加向量到群索引
        index, id_map = self._load_group_index(group_id)
        index.add(embedding.reshape(1, -1))
        id_map.append(memory_id)
        self._group_indices[group_id] = (index, id_map)
        self._save_group_index(group_id)
    
    def search_memory(
        self, 
        user_id: str, 
        query_text: str,
        group_id: str = None,
        k: Optional[int] = None,
        max_tokens: int = 500,
        cross_scene: bool = False
    ) -> str:
        """
        检索记忆（双数据库架构，支持跨群组检索）
        
        Args:
            user_id: 用户ID
            query_text: 查询文本
            group_id: 群ID（如果是群聊）
            k: 检索数量
            max_tokens: 最大token数
            cross_scene: 是否跨场景检索（检索用户在所有群的记忆）
        
        Returns:
            格式化的记忆文本
        """
        if not self.enabled:
            return ""
        
        # 每次检索前重新读取阈值
        current_threshold = ConfigManager.get_bot_config().storage.similarity_threshold
        if current_threshold != self.similarity_threshold:
            logger.debug(f"检测到阈值变化: {self.similarity_threshold} → {current_threshold}")
            self.similarity_threshold = current_threshold
        
        # 短文本过滤
        query_stripped = query_text.strip()
        if len(query_stripped) < 4:
            return ""
        
        skip_patterns = {"嗯", "哦", "好", "啊", "呢", "吧", "了", "在吗", "在不", "你好"}
        if query_stripped in skip_patterns:
            return ""
        
        try:
            # 生成查询向量
            query_vec = self.embedding_client.get_embedding(query_text)
            query_vec = self._normalize_vector(query_vec)
            
            if group_id:
                # 群聊检索：从群数据库检索
                return self._search_group_memory(group_id, user_id, query_vec, k, max_tokens, cross_scene)
            else:
                # 私聊检索：从用户私聊数据库检索
                return self._search_private_memory(user_id, query_vec, k, max_tokens, cross_scene)
        
        except Exception as e:
            logger.error(f"❌ 检索记忆失败: {e}")
            return ""
    
    def _search_private_memory(
        self,
        user_id: str,
        query_vec: np.ndarray,
        k: Optional[int],
        max_tokens: int,
        cross_scene: bool
    ) -> str:
        """检索用户私聊记忆"""
        db_path = self._get_private_db_path(user_id)
        if not db_path.exists():
            logger.info(f"🔍 [{user_id}] 用户数据库不存在")
            return ""
        
        # 加载索引
        index, id_map = self._load_private_index(user_id)
        
        if index.ntotal == 0:
            logger.info(f"🔍 [{user_id}] 私聊索引为空")
            return ""
        
        # FAISS 检索
        fetch_count = (k or self.retrieve_count) + 5
        distances, indices = index.search(
            query_vec.reshape(1, -1),
            min(fetch_count, index.ntotal)
        )
        
        if len(indices[0]) == 0:
            return ""
        
        # 从数据库拉取元数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        valid_results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx >= len(id_map):
                continue
            
            memory_ref = id_map[idx]
            similarity = float(dist)
            
            if similarity < self.similarity_threshold:
                continue
            
            # 判断是私聊记忆还是群聊记忆
            if isinstance(memory_ref, tuple):
                # 群聊记忆：('group', memory_id)
                if not cross_scene:
                    continue  # 私聊时不检索群聊记忆（除非开启跨场景）
                
                table_name = 'group_memories'
                memory_id = memory_ref[1]
            else:
                # 私聊记忆：memory_id
                table_name = 'private_memories'
                memory_id = memory_ref
            
            # 拉取元数据
            cursor.execute(f"""
                SELECT id, role, content, timestamp
                FROM {table_name} WHERE id = ?
            """, (memory_id,))
            
            row = cursor.fetchone()
            if row:
                valid_results.append({
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "timestamp": row[3],
                    "similarity": similarity,
                    "source": table_name
                })
        
        conn.close()
        
        if not valid_results:
            logger.info(f"🔍 [{user_id}] 未检索到符合条件的记忆（阈值: {self.similarity_threshold}）")
            return ""
        
        # 时间权重重排序
        current_time = int(time.time())
        tau = 7 * 24 * 3600
        
        for r in valid_results:
            age = max(current_time - r["timestamp"], 0)
            import math
            freshness = math.exp(-age / tau)
            r["score"] = r["similarity"] * (1 + 0.3 * freshness)
        
        valid_results.sort(key=lambda x: x["score"], reverse=True)
        
        # 格式化输出
        return self._format_memory_results(valid_results, max_tokens, user_id)
    
    def _search_group_memory(
        self,
        group_id: str,
        user_id: str,
        query_vec: np.ndarray,
        k: Optional[int],
        max_tokens: int,
        cross_scene: bool
    ) -> str:
        """检索群聊记忆（支持跨群检索）"""
        db_path = self._get_group_db_path(group_id)
        if not db_path.exists():
            logger.info(f"🔍 [群{group_id}] 群数据库不存在")
            return ""
        
        # 加载群索引
        index, id_map = self._load_group_index(group_id)
        
        if index.ntotal == 0:
            logger.info(f"🔍 [群{group_id}] 群索引为空")
            return ""
        
        # FAISS 检索
        fetch_count = (k or self.retrieve_count) + 5
        distances, indices = index.search(
            query_vec.reshape(1, -1),
            min(fetch_count, index.ntotal)
        )
        
        if len(indices[0]) == 0:
            return ""
        
        # 从数据库拉取元数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        valid_results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx >= len(id_map):
                continue
            
            memory_id = id_map[idx]
            similarity = float(dist)
            
            if similarity < self.similarity_threshold:
                continue
            
            # 拉取元数据
            cursor.execute("""
                SELECT id, user_id, role, content, timestamp, sender_name
                FROM member_memories WHERE id = ?
            """, (memory_id,))
            
            row = cursor.fetchone()
            if row:
                valid_results.append({
                    "id": row[0],
                    "user_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "timestamp": row[4],
                    "sender_name": row[5],
                    "similarity": similarity
                })
        
        conn.close()
        
        # 如果开启跨场景检索，还要检索该用户在其他群的记忆
        if cross_scene:
            user_group_results = self._search_user_in_other_groups(user_id, group_id, query_vec, k)
            valid_results.extend(user_group_results)
        
        if not valid_results:
            logger.info(f"🔍 [群{group_id}] 未检索到符合条件的记忆（阈值: {self.similarity_threshold}）")
            return ""
        
        # 时间权重重排序
        current_time = int(time.time())
        tau = 7 * 24 * 3600
        
        for r in valid_results:
            age = max(current_time - r["timestamp"], 0)
            import math
            freshness = math.exp(-age / tau)
            r["score"] = r["similarity"] * (1 + 0.3 * freshness)
        
        valid_results.sort(key=lambda x: x["score"], reverse=True)
        
        # 格式化输出
        return self._format_memory_results(valid_results, max_tokens, f"群{group_id}")
    
    def _search_user_in_other_groups(
        self,
        user_id: str,
        current_group_id: str,
        query_vec: np.ndarray,
        k: Optional[int]
    ) -> List[Dict]:
        """检索用户在其他群的记忆（跨群检索）"""
        user_db_path = self._get_private_db_path(user_id)
        if not user_db_path.exists():
            return []
        
        # 从用户数据库的 group_memories 表检索
        conn = sqlite3.connect(str(user_db_path))
        cursor = conn.cursor()
        
        # 获取用户在其他群的记忆
        cursor.execute("""
            SELECT id, group_id, content, timestamp
            FROM group_memories
            WHERE group_id != ?
            ORDER BY timestamp DESC
            LIMIT 50
        """, (current_group_id,))
        
        other_group_memories = cursor.fetchall()
        conn.close()
        
        if not other_group_memories:
            return []
        
        # 计算相似度
        results = []
        for memory_id, group_id, content, timestamp in other_group_memories:
            try:
                mem_vec = self.embedding_client.get_embedding(content)
                mem_vec = self._normalize_vector(mem_vec)
                similarity = float(np.dot(query_vec, mem_vec))
                
                if similarity >= self.similarity_threshold:
                    results.append({
                        "id": memory_id,
                        "user_id": user_id,
                        "role": "Pair",
                        "content": content,
                        "timestamp": timestamp,
                        "sender_name": f"[来自群{group_id}]",
                        "similarity": similarity
                    })
            except Exception as e:
                logger.debug(f"计算相似度失败: {e}")
                continue
        
        return results
    
    def _format_memory_results(self, results: List[Dict], max_tokens: int, context: str) -> str:
        """格式化记忆检索结果"""
        memory_lines = []
        total_chars = 0
        max_chars = max_tokens * 2
        
        from datetime import datetime
        
        for r in results:
            content = r["content"]
            if total_chars + len(content) > max_chars:
                break
            
            # 格式化时间戳
            timestamp = r["timestamp"]
            time_str = datetime.fromtimestamp(timestamp).strftime("%m-%d %H:%M")
            
            # 添加发送者信息（如果有）
            sender_info = ""
            if "sender_name" in r and r["sender_name"]:
                sender_info = f" {r['sender_name']}"
            
            memory_lines.append(f"- [{time_str}]{sender_info} [{r['role']}] {content}")
            total_chars += len(content)
        
        if not memory_lines:
            return ""
        
        result_text = "\n".join(memory_lines)
        logger.info(f"🔍 [{context}] 检索到 {len(memory_lines)} 条记忆")
        return result_text
    
    def search_knowledge(
        self, 
        query_text: str, 
        k: Optional[int] = None,
        max_tokens: int = 400
    ) -> str:
        """检索知识库"""
        if not self.enabled:
            logger.debug("知识库检索未启用")
            self._last_kb_search_stats = {"enabled": False}
            return ""
        
        query_stripped = query_text.strip()
        if len(query_stripped) < 3:
            logger.debug(f"查询文本过短（{len(query_stripped)}字），跳过检索")
            self._last_kb_search_stats = {"skipped": "query_too_short", "query_length": len(query_stripped)}
            return ""
        
        skip_patterns = {"嗯", "哦", "好", "啊", "呢", "吧", "了"}
        if query_stripped in skip_patterns:
            logger.debug(f"查询文本 '{query_stripped}' 在跳过列表中")
            self._last_kb_search_stats = {"skipped": "skip_pattern", "query": query_stripped}
            return ""
        
        logger.info(f"📚 [知识库检索] 查询: {query_text[:50]}")
        
        try:
            # 生成查询向量
            query_vec = self.embedding_client.get_embedding(query_text)
            query_vec = self._normalize_vector(query_vec)
            
            # FAISS 检索
            fetch_count = (k or 4) * 2
            distances, indices = self.kb_index.search(
                query_vec.reshape(1, -1),
                min(fetch_count, self.kb_index.ntotal)
            )
            
            logger.info(f"   FAISS 检索: 请求 {fetch_count} 条，返回 {len(indices[0])} 条")
            
            if len(indices[0]) == 0:
                logger.info(f"   未找到任何结果")
                self._last_kb_search_stats = {
                    "total_in_db": self.kb_index.ntotal,
                    "fetched": 0,
                    "passed": 0,
                    "filtered": 0
                }
                return ""
            
            # 从 SQLite 拉取元数据
            conn = sqlite3.connect(str(self.kb_db_path))
            cursor = conn.cursor()
            
            # 知识库阈值
            kb_threshold = getattr(ConfigManager.get_bot_config().storage, 'kb_similarity_threshold', 0.45)
            logger.info(f"   相似度阈值: {kb_threshold}")
            
            valid_results = []
            filtered_count = 0
            
            for idx, dist in zip(indices[0], distances[0]):
                if idx >= len(self.kb_id_map):
                    continue
                
                kb_id = self.kb_id_map[idx]
                similarity = float(dist)
                
                logger.debug(f"     知识 {kb_id}: 相似度 {similarity:.3f}")
                
                if similarity < kb_threshold:
                    logger.debug(f"       ✗ 相似度 {similarity:.3f} < 阈值 {kb_threshold}，过滤")
                    filtered_count += 1
                    continue
                
                # 拉取元数据
                cursor.execute("""
                    SELECT id, source, content, title
                    FROM knowledge WHERE id = ?
                """, (kb_id,))
                
                row = cursor.fetchone()
                if row:
                    valid_results.append({
                        "source": row[1],
                        "content": row[2],
                        "title": row[3] or row[1],
                        "similarity": similarity
                    })
                    logger.debug(f"       ✓ 知识 {kb_id} 通过: {row[3][:30]}...")
            
            conn.close()
            
            logger.info(f"   过滤结果: {len(valid_results)} 条通过，{filtered_count} 条被过滤")
            
            # 保存检索统计
            self._last_kb_search_stats = {
                "total_in_db": self.kb_index.ntotal,
                "fetched": len(indices[0]),
                "passed": len(valid_results),
                "filtered": filtered_count,
                "threshold": kb_threshold
            }
            
            if not valid_results:
                logger.info(f"   无符合条件的知识（阈值: {kb_threshold}）")
                return ""
            
            # 格式化输出
            knowledge_lines = []
            for i, r in enumerate(valid_results[:(k or 4)], 1):
                knowledge_lines.append(
                    f"{i}. 标题：{r['title']}\n"
                    f"   内容：{r['content']}\n"
                    f"   相关性：{r['similarity']:.2f}"
                )
            
            result_text = "\n".join(knowledge_lines)
            logger.info(f"✅ [知识库检索] 返回 {len(knowledge_lines)} 条知识（共 {len(result_text)} 字符）")
            
            return result_text
        
        except Exception as e:
            logger.error(f"❌ 检索知识库失败: {e}")
            self._last_kb_search_stats = {"error": str(e)}
            return ""
    
    def clear_user_memory(self, user_id: str) -> bool:
        """清空用户记忆（双数据库架构）"""
        try:
            # 删除用户的私聊数据库
            db_path = self._get_private_db_path(user_id)
            if db_path.exists():
                db_path.unlink()
                logger.info(f"🗑️ 已删除用户 {user_id} 的私聊数据库")
            
            # 删除用户的私聊索引
            index_path, id_map_path = self._get_private_index_path(user_id)
            if index_path.exists():
                index_path.unlink()
            if id_map_path.exists():
                id_map_path.unlink()
            
            # 清除缓存
            if user_id in self._private_indices:
                del self._private_indices[user_id]
            
            logger.warning(f"🗑️ 已清空用户 {user_id} 的所有记忆")
            return True
        except Exception as e:
            logger.error(f"❌ 清空记忆失败: {e}")
            return False
    
    def clear_group_memory(self, group_id: str) -> bool:
        """清空群聊记忆"""
        try:
            # 删除群的数据库
            db_path = self._get_group_db_path(group_id)
            if db_path.exists():
                db_path.unlink()
                logger.info(f"🗑️ 已删除群 {group_id} 的数据库")
            
            # 删除群的索引
            index_path, id_map_path = self._get_group_index_path(group_id)
            if index_path.exists():
                index_path.unlink()
            if id_map_path.exists():
                id_map_path.unlink()
            
            # 清除缓存
            if group_id in self._group_indices:
                del self._group_indices[group_id]
            
            logger.warning(f"🗑️ 已清空群 {group_id} 的所有记忆")
            return True
        except Exception as e:
            logger.error(f"❌ 清空群记忆失败: {e}")
            return False
    
    def _rebuild_memory_index(self):
        """重建记忆索引（已废弃，双数据库架构不需要）"""
        logger.warning("双数据库架构不需要重建全局索引")
        pass
    
    def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户记忆统计（双数据库架构）"""
        try:
            db_path = self._get_private_db_path(user_id)
            if not db_path.exists():
                return {"total": 0, "private": 0, "group": 0}
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 私聊记忆数
            cursor.execute("SELECT COUNT(*) FROM private_memories")
            private_count = cursor.fetchone()[0]
            
            # 群聊记忆数
            cursor.execute("SELECT COUNT(*) FROM group_memories")
            group_count = cursor.fetchone()[0]
            
            # 按群统计
            cursor.execute("""
                SELECT group_id, COUNT(*) 
                FROM group_memories 
                GROUP BY group_id
            """)
            by_group = {row[0]: row[1] for row in cursor.fetchall()}
            
            conn.close()
            
            return {
                "total": private_count + group_count,
                "private": private_count,
                "group": group_count,
                "by_group": by_group,
                "last_updated": int(time.time())
            }
        except Exception as e:
            logger.error(f"❌ 获取统计失败: {e}")
            return {"total": 0, "error": str(e)}
    
    def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """获取群聊记忆统计"""
        try:
            db_path = self._get_group_db_path(group_id)
            if not db_path.exists():
                return {"total": 0, "members": {}}
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 总记忆数
            cursor.execute("SELECT COUNT(*) FROM member_memories")
            total = cursor.fetchone()[0]
            
            # 按用户统计
            cursor.execute("""
                SELECT user_id, COUNT(*) 
                FROM member_memories 
                GROUP BY user_id
            """)
            by_user = {row[0]: row[1] for row in cursor.fetchall()}
            
            conn.close()
            
            return {
                "total": total,
                "members": by_user,
                "last_updated": int(time.time())
            }
        except Exception as e:
            logger.error(f"❌ 获取群统计失败: {e}")
            return {"total": 0, "error": str(e)}
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取全局统计"""
        try:
            # 统计私聊数据库数量
            private_dbs = list(self.private_db_dir.glob("user_*.db"))
            
            # 统计群聊数据库数量
            group_dbs = list(self.group_db_dir.glob("group_*.db"))
            
            # 统计总记忆数
            total_private = 0
            total_group = 0
            
            for db_path in private_dbs:
                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM private_memories")
                    total_private += cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM group_memories")
                    total_group += cursor.fetchone()[0]
                    conn.close()
                except Exception:
                    pass
            
            for db_path in group_dbs:
                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM member_memories")
                    total_group += cursor.fetchone()[0]
                    conn.close()
                except Exception:
                    pass
            
            return {
                "user_count": len(private_dbs),
                "group_count": len(group_dbs),
                "total_private_memories": total_private,
                "total_group_memories": total_group,
                "total_memories": total_private + total_group
            }
        except Exception as e:
            logger.error(f"❌ 获取全局统计失败: {e}")
            return {"error": str(e)}


# 全局单例
_vector_service: Optional[FAISSVectorService] = None


def get_vector_service() -> FAISSVectorService:
    """获取全局向量服务单例"""
    global _vector_service
    if _vector_service is None:
        _vector_service = FAISSVectorService()
    return _vector_service
