"""
关系知识图谱存储
使用 SQLite 存储节点和边
"""
import sqlite3
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from src.core.logger import logger


class GraphStorage:
    """知识图谱存储（节点+边）"""
    
    def __init__(self, db_path: str = "./data/knowledge_graph.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"✅ 知识图谱存储初始化: {self.db_path}")
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # 节点表（实体）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_type TEXT,
                properties TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, entity)
            )
        """)
        
        # 边表（关系）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation TEXT NOT NULL,
                properties TEXT,
                weight REAL DEFAULT 1.0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, source_entity, target_entity, relation)
            )
        """)
        
        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_user ON nodes(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_entity ON nodes(entity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_user ON edges(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_entity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_entity)")
        
        conn.commit()
        conn.close()
    
    def add_node(
        self, 
        user_id: str, 
        entity: str, 
        entity_type: str = None,
        properties: Dict[str, Any] = None,
        alias: str = None
    ) -> int:
        """
        添加或更新节点(增强版: 支持别名/指代)
        
        Args:
            alias: 别名或指代(如"她"、"那个人")
        """
        import time
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        timestamp = int(time.time())
        
        # 将别名存入 properties
        props = properties or {}
        if alias:
            # 如果已有别名列表，追加；否则创建新列表
            existing_aliases = props.get('aliases', [])
            if isinstance(existing_aliases, list):
                if alias not in existing_aliases:
                    existing_aliases.append(alias)
                props['aliases'] = existing_aliases
            else:
                props['aliases'] = [alias]
        
        props_json = json.dumps(props, ensure_ascii=False)
        
        try:
            cursor.execute("""
                INSERT INTO nodes (user_id, entity, entity_type, properties, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, entity) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    properties = excluded.properties,
                    updated_at = excluded.updated_at
            """, (user_id, entity, entity_type, props_json, timestamp, timestamp))
            
            node_id = cursor.lastrowid
            conn.commit()
            return node_id
        finally:
            conn.close()
    
    def add_edge(
        self,
        user_id: str,
        source: str,
        target: str,
        relation: str,
        properties: Dict[str, Any] = None,
        weight: float = 1.0,
        time_ref: str = None
    ) -> int:
        """
        添加或更新边(增强版: 支持时间指代)
        
        Args:
            time_ref: 时间指代(如"昨天"、"上次"、"最近")
        """
        import time
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        timestamp = int(time.time())
        
        # 将时间指代存入 properties
        props = properties or {}
        if time_ref:
            props['time_ref'] = time_ref
            props['timestamp'] = timestamp  # 记录实际时间戳
        
        props_json = json.dumps(props, ensure_ascii=False)
        
        try:
            cursor.execute("""
                INSERT INTO edges (user_id, source_entity, target_entity, relation, properties, weight, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, source_entity, target_entity, relation) DO UPDATE SET
                    properties = excluded.properties,
                    weight = weight + 0.1,
                    updated_at = excluded.updated_at
            """, (user_id, source, target, relation, props_json, weight, timestamp, timestamp))
            
            edge_id = cursor.lastrowid
            conn.commit()
            return edge_id
        finally:
            conn.close()
    
    def get_neighbors(self, user_id: str, entity: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """获取实体的邻居节点（多跳）"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        visited = set()
        results = []
        
        def _traverse(current_entity: str, depth: int):
            if depth > max_depth or current_entity in visited:
                return
            
            visited.add(current_entity)
            
            # 查找出边
            cursor.execute("""
                SELECT target_entity, relation, weight, properties
                FROM edges
                WHERE user_id = ? AND source_entity = ?
                ORDER BY weight DESC
                LIMIT 10
            """, (user_id, current_entity))
            
            for row in cursor.fetchall():
                target, relation, weight, props = row
                results.append({
                    "source": current_entity,
                    "target": target,
                    "relation": relation,
                    "weight": weight,
                    "depth": depth,
                    "properties": json.loads(props) if props else {}
                })
                
                if depth < max_depth:
                    _traverse(target, depth + 1)
        
        _traverse(entity, 1)
        conn.close()
        
        return results
    
    def search_entities(self, user_id: str, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索实体（模糊匹配）"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT entity, entity_type, properties, updated_at
            FROM nodes
            WHERE user_id = ? AND entity LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (user_id, f"%{keyword}%", limit))
        
        results = []
        for row in cursor.fetchall():
            entity, entity_type, props, updated_at = row
            results.append({
                "entity": entity,
                "entity_type": entity_type,
                "properties": json.loads(props) if props else {},
                "updated_at": updated_at
            })
        
        conn.close()
        return results
    
    def get_user_graph_stats(self, user_id: str) -> Dict[str, int]:
        """获取用户图谱统计"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM nodes WHERE user_id = ?", (user_id,))
        node_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM edges WHERE user_id = ?", (user_id,))
        edge_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "nodes": node_count,
            "edges": edge_count
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # 总节点数
        cursor.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = cursor.fetchone()[0]
        
        # 总边数
        cursor.execute("SELECT COUNT(*) FROM edges")
        total_edges = cursor.fetchone()[0]
        
        # 用户数
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM nodes")
        total_users = cursor.fetchone()[0]
        
        # 实体类型数
        cursor.execute("SELECT COUNT(DISTINCT entity_type) FROM nodes WHERE entity_type IS NOT NULL")
        entity_types = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_users": total_users,
            "entity_types": entity_types
        }
    
    def get_users(self) -> List[Dict[str, Any]]:
        """获取所有用户及其节点数"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, COUNT(*) as node_count
            FROM nodes
            GROUP BY user_id
            ORDER BY node_count DESC
        """)
        
        users = []
        for row in cursor.fetchall():
            users.append({
                "user_id": row[0],
                "node_count": row[1]
            })
        
        conn.close()
        return users
    
    def get_graph_data(
        self,
        user_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取图谱数据（用于可视化）"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # 构建查询条件
        node_conditions = []
        node_params = []
        
        if user_id:
            node_conditions.append("user_id = ?")
            node_params.append(user_id)
        
        if entity_type:
            node_conditions.append("entity_type = ?")
            node_params.append(entity_type)
        
        if search:
            node_conditions.append("entity LIKE ?")
            node_params.append(f"%{search}%")
        
        node_where = " AND ".join(node_conditions) if node_conditions else "1=1"
        
        # 查询节点
        cursor.execute(f"""
            SELECT id, user_id, entity, entity_type, properties, created_at, updated_at
            FROM nodes
            WHERE {node_where}
            ORDER BY updated_at DESC
            LIMIT 500
        """, node_params)
        
        nodes = []
        node_ids = set()
        for row in cursor.fetchall():
            node_id, uid, entity, etype, props, created, updated = row
            nodes.append({
                "id": node_id,
                "user_id": uid,
                "entity": entity,
                "entity_type": etype or "其他",
                "properties": json.loads(props) if props else {},
                "created_at": created,
                "updated_at": updated
            })
            node_ids.add(node_id)
        
        # 查询边（只查询节点之间的边）
        if node_ids:
            # 获取实体名称到 ID 的映射
            entity_to_id = {n["entity"]: n["id"] for n in nodes}
            
            edge_conditions = []
            edge_params = []
            
            if user_id:
                edge_conditions.append("user_id = ?")
                edge_params.append(user_id)
            
            edge_where = " AND ".join(edge_conditions) if edge_conditions else "1=1"
            
            cursor.execute(f"""
                SELECT id, user_id, source_entity, target_entity, relation, properties, weight, created_at
                FROM edges
                WHERE {edge_where}
                LIMIT 1000
            """, edge_params)
            
            edges = []
            for row in cursor.fetchall():
                edge_id, uid, source, target, relation, props, weight, created = row
                
                # 只包含在节点集合中的边
                if source in entity_to_id and target in entity_to_id:
                    edges.append({
                        "id": edge_id,
                        "user_id": uid,
                        "source": source,
                        "target": target,
                        "source_id": entity_to_id[source],
                        "target_id": entity_to_id[target],
                        "relation": relation,
                        "properties": json.loads(props) if props else {},
                        "weight": weight,
                        "created_at": created
                    })
        else:
            edges = []
        
        conn.close()
        
        return {
            "nodes": nodes,
            "edges": edges
        }
    
    def clear_user_graph(self, user_id: str) -> int:
        """清空指定用户的图谱"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM nodes WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM nodes WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM edges WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
        
        logger.warning(f"🗑️ 已清空用户 {user_id} 的图谱（{count} 个节点）")
        return count
    
    def clear_all_graph(self) -> int:
        """清空所有图谱"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM nodes")
        count = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM nodes")
        cursor.execute("DELETE FROM edges")
        
        conn.commit()
        conn.close()
        
        logger.warning(f"🗑️ 已清空所有图谱（{count} 个节点）")
        return count
    
    def cleanup_orphan_nodes(self, user_id: str = None) -> int:
        """
        清理孤立节点（没有任何关系的节点）
        
        Args:
            user_id: 指定用户 ID，如果为 None 则清理所有用户
            
        Returns:
            删除的节点数量
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            if user_id:
                # 查找孤立节点（该用户的节点，既不是源也不是目标）
                cursor.execute("""
                    SELECT entity FROM nodes
                    WHERE user_id = ?
                    AND entity NOT IN (
                        SELECT DISTINCT source_entity FROM edges WHERE user_id = ?
                        UNION
                        SELECT DISTINCT target_entity FROM edges WHERE user_id = ?
                    )
                """, (user_id, user_id, user_id))
            else:
                # 查找所有孤立节点
                cursor.execute("""
                    SELECT user_id, entity FROM nodes
                    WHERE (user_id, entity) NOT IN (
                        SELECT user_id, source_entity FROM edges
                        UNION
                        SELECT user_id, target_entity FROM edges
                    )
                """)
            
            orphans = cursor.fetchall()
            
            if not orphans:
                return 0
            
            # 删除孤立节点
            if user_id:
                orphan_entities = [row[0] for row in orphans]
                placeholders = ','.join('?' * len(orphan_entities))
                cursor.execute(f"""
                    DELETE FROM nodes
                    WHERE user_id = ? AND entity IN ({placeholders})
                """, [user_id] + orphan_entities)
                
                deleted = cursor.rowcount
                logger.info(f"🧹 [图谱清理] 用户 {user_id}: 删除 {deleted} 个孤立节点")
            else:
                # 按用户分组删除
                deleted = 0
                user_orphans = {}
                for row in orphans:
                    uid, entity = row
                    if uid not in user_orphans:
                        user_orphans[uid] = []
                    user_orphans[uid].append(entity)
                
                for uid, entities in user_orphans.items():
                    placeholders = ','.join('?' * len(entities))
                    cursor.execute(f"""
                        DELETE FROM nodes
                        WHERE user_id = ? AND entity IN ({placeholders})
                    """, [uid] + entities)
                    deleted += cursor.rowcount
                
                logger.info(f"🧹 [图谱清理] 全局: 删除 {deleted} 个孤立节点（{len(user_orphans)} 个用户）")
            
            conn.commit()
            return deleted
            
        finally:
            conn.close()
    
    def cleanup_low_connection_nodes(self, user_id: str = None, threshold: int = 1) -> int:
        """
        清理低连接节点（关系数 <= threshold 的节点）
        
        Args:
            user_id: 指定用户 ID，如果为 None 则清理所有用户
            threshold: 关系数阈值，默认为 1（仅1条关系）
            
        Returns:
            删除的节点数量
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            # 查找低连接节点
            if user_id:
                cursor.execute("""
                    SELECT entity,
                           (SELECT COUNT(*) FROM edges e WHERE e.user_id = n.user_id AND e.source_entity = n.entity) +
                           (SELECT COUNT(*) FROM edges e WHERE e.user_id = n.user_id AND e.target_entity = n.entity) as edge_count
                    FROM nodes n
                    WHERE n.user_id = ? AND edge_count <= ? AND edge_count > 0
                """, (user_id, threshold))
            else:
                cursor.execute("""
                    SELECT user_id, entity,
                           (SELECT COUNT(*) FROM edges e WHERE e.user_id = n.user_id AND e.source_entity = n.entity) +
                           (SELECT COUNT(*) FROM edges e WHERE e.user_id = n.user_id AND e.target_entity = n.entity) as edge_count
                    FROM nodes n
                    WHERE edge_count <= ? AND edge_count > 0
                """, (threshold,))
            
            low_conn_nodes = cursor.fetchall()
            
            if not low_conn_nodes:
                return 0
            
            # 删除低连接节点及其关系
            deleted = 0
            
            if user_id:
                for (entity, edge_count) in low_conn_nodes:
                    # 删除相关的边
                    cursor.execute("""
                        DELETE FROM edges
                        WHERE user_id = ? AND (source_entity = ? OR target_entity = ?)
                    """, (user_id, entity, entity))
                    
                    # 删除节点
                    cursor.execute("""
                        DELETE FROM nodes
                        WHERE user_id = ? AND entity = ?
                    """, (user_id, entity))
                    
                    deleted += 1
                
                logger.info(f"🧹 [图谱清理] 用户 {user_id}: 删除 {deleted} 个低连接节点（≤{threshold}条关系）")
            else:
                user_counts = {}
                for (uid, entity, edge_count) in low_conn_nodes:
                    # 删除相关的边
                    cursor.execute("""
                        DELETE FROM edges
                        WHERE user_id = ? AND (source_entity = ? OR target_entity = ?)
                    """, (uid, entity, entity))
                    
                    # 删除节点
                    cursor.execute("""
                        DELETE FROM nodes
                        WHERE user_id = ? AND entity = ?
                    """, (uid, entity))
                    
                    deleted += 1
                    user_counts[uid] = user_counts.get(uid, 0) + 1
                
                logger.info(f"🧹 [图谱清理] 全局: 删除 {deleted} 个低连接节点（≤{threshold}条关系，{len(user_counts)} 个用户）")
            
            conn.commit()
            return deleted
            
        finally:
            conn.close()
    
    def merge_duplicate_entities(self, user_id: str = None) -> int:
        """
        合并重复实体（基于相似度和别名）
        
        策略：
        1. 查找名称相似的实体（编辑距离 <= 1）
        2. 查找互为别名的实体
        3. 合并节点属性和关系
        
        Args:
            user_id: 指定用户 ID，如果为 None 则处理所有用户
            
        Returns:
            合并的实体数量
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            # 获取需要处理的用户列表
            if user_id:
                users = [user_id]
            else:
                cursor.execute("SELECT DISTINCT user_id FROM nodes")
                users = [row[0] for row in cursor.fetchall()]
            
            total_merged = 0
            
            for uid in users:
                # 获取该用户的所有实体
                cursor.execute("""
                    SELECT entity, entity_type, properties
                    FROM nodes
                    WHERE user_id = ?
                    ORDER BY entity
                """, (uid,))
                
                entities = cursor.fetchall()
                
                if len(entities) < 2:
                    continue
                
                # 查找重复实体
                merged_count = 0
                processed = set()
                
                for i, (entity1, type1, props1) in enumerate(entities):
                    if entity1 in processed:
                        continue
                    
                    props1_dict = json.loads(props1) if props1 else {}
                    aliases1 = set(props1_dict.get('aliases', []))
                    
                    duplicates = []
                    
                    for j in range(i + 1, len(entities)):
                        entity2, type2, props2 = entities[j]
                        
                        if entity2 in processed:
                            continue
                        
                        props2_dict = json.loads(props2) if props2 else {}
                        aliases2 = set(props2_dict.get('aliases', []))
                        
                        # 判断是否重复
                        is_duplicate = False
                        
                        # 1. 名称完全相同（不同大小写）
                        if entity1.lower() == entity2.lower() and entity1 != entity2:
                            is_duplicate = True
                        
                        # 2. 互为别名
                        elif entity2 in aliases1 or entity1 in aliases2:
                            is_duplicate = True
                        
                        # 3. 编辑距离 <= 1（仅对短实体）
                        elif len(entity1) <= 4 and len(entity2) <= 4:
                            if self._edit_distance(entity1, entity2) <= 1:
                                is_duplicate = True
                        
                        if is_duplicate:
                            duplicates.append((entity2, type2, props2_dict))
                            processed.add(entity2)
                    
                    # 合并重复实体
                    if duplicates:
                        merged_count += len(duplicates)
                        self._merge_entities(cursor, uid, entity1, duplicates)
                
                if merged_count > 0:
                    total_merged += merged_count
                    logger.info(f"🔗 [图谱清理] 用户 {uid}: 合并 {merged_count} 个重复实体")
            
            conn.commit()
            
            if total_merged > 0:
                logger.info(f"🔗 [图谱清理] 全局: 合并 {total_merged} 个重复实体")
            
            return total_merged
            
        finally:
            conn.close()
    
    def _edit_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离（Levenshtein 距离）"""
        if len(s1) < len(s2):
            return self._edit_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _merge_entities(
        self,
        cursor: sqlite3.Cursor,
        user_id: str,
        main_entity: str,
        duplicates: List[Tuple[str, str, Dict[str, Any]]]
    ):
        """
        合并实体（内部方法）
        
        Args:
            cursor: 数据库游标
            user_id: 用户 ID
            main_entity: 主实体（保留）
            duplicates: 重复实体列表 [(entity, type, properties), ...]
        """
        import time
        
        # 1. 合并别名
        cursor.execute("""
            SELECT properties FROM nodes
            WHERE user_id = ? AND entity = ?
        """, (user_id, main_entity))
        
        row = cursor.fetchone()
        if not row:
            return
        
        main_props = json.loads(row[0]) if row[0] else {}
        main_aliases = set(main_props.get('aliases', []))
        
        # 收集所有别名
        for dup_entity, _, dup_props in duplicates:
            main_aliases.add(dup_entity)  # 重复实体名作为别名
            main_aliases.update(dup_props.get('aliases', []))
        
        # 移除主实体名（避免自己是自己的别名）
        main_aliases.discard(main_entity)
        
        main_props['aliases'] = list(main_aliases)
        
        # 更新主实体
        cursor.execute("""
            UPDATE nodes
            SET properties = ?, updated_at = ?
            WHERE user_id = ? AND entity = ?
        """, (json.dumps(main_props, ensure_ascii=False), int(time.time()), user_id, main_entity))
        
        # 2. 更新关系（将重复实体的关系指向主实体）
        for dup_entity, _, _ in duplicates:
            # 更新出边（使用 INSERT OR IGNORE 避免冲突）
            cursor.execute("""
                INSERT OR IGNORE INTO edges (user_id, source_entity, target_entity, relation, properties, weight, created_at, updated_at)
                SELECT user_id, ?, target_entity, relation, properties, weight, created_at, updated_at
                FROM edges
                WHERE user_id = ? AND source_entity = ?
            """, (main_entity, user_id, dup_entity))
            
            # 删除旧的出边
            cursor.execute("""
                DELETE FROM edges
                WHERE user_id = ? AND source_entity = ?
            """, (user_id, dup_entity))
            
            # 更新入边（使用 INSERT OR IGNORE 避免冲突）
            cursor.execute("""
                INSERT OR IGNORE INTO edges (user_id, source_entity, target_entity, relation, properties, weight, created_at, updated_at)
                SELECT user_id, source_entity, ?, relation, properties, weight, created_at, updated_at
                FROM edges
                WHERE user_id = ? AND target_entity = ?
            """, (main_entity, user_id, dup_entity))
            
            # 删除旧的入边
            cursor.execute("""
                DELETE FROM edges
                WHERE user_id = ? AND target_entity = ?
            """, (user_id, dup_entity))
            
            # 删除重复实体节点
            cursor.execute("""
                DELETE FROM nodes
                WHERE user_id = ? AND entity = ?
            """, (user_id, dup_entity))
        
        # 3. 删除自环边（source = target = main_entity）
        cursor.execute("""
            DELETE FROM edges
            WHERE user_id = ? AND source_entity = ? AND target_entity = ?
        """, (user_id, main_entity, main_entity))


# 全局单例
_graph_storage: Optional[GraphStorage] = None


def get_graph_storage() -> GraphStorage:
    """获取全局图谱存储单例"""
    global _graph_storage
    if _graph_storage is None:
        _graph_storage = GraphStorage()
    return _graph_storage
