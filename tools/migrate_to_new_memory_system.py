"""
记忆系统迁移工具 - 从旧结构迁移到新的双数据库结构

旧结构:
- data/chroma_db/memory.db (单一数据库)
- data/chroma_db/memory.faiss (单一索引)

新结构:
- data/memory_v2/private/{user_id}/
  - private.db (私聊数据)
  - private.faiss (私聊索引)
  - groups.db (该用户在各群的发言)
  - groups.faiss (群聊索引)
  
- data/memory_v2/groups/{group_id}/
  - members.db (群成员数据)
  - members.faiss (群索引)
"""
import sqlite3
import shutil
import pickle
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.logger import logger


def backup_old_database():
    """备份旧数据库"""
    old_db = project_root / "data/chroma_db/memory.db"
    old_faiss = project_root / "data/chroma_db/memory.faiss"
    old_id_map = project_root / "data/chroma_db/memory_id_map.pkl"
    
    if not old_db.exists():
        logger.error("❌ 旧数据库不存在")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = project_root / f"data/backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📦 备份旧数据到: {backup_dir}")
    
    if old_db.exists():
        shutil.copy2(old_db, backup_dir / "memory.db")
        logger.info(f"  ✓ memory.db")
    
    if old_faiss.exists():
        shutil.copy2(old_faiss, backup_dir / "memory.faiss")
        logger.info(f"  ✓ memory.faiss")
    
    if old_id_map.exists():
        shutil.copy2(old_id_map, backup_dir / "memory_id_map.pkl")
        logger.info(f"  ✓ memory_id_map.pkl")
    
    return True


def analyze_old_database():
    """分析旧数据库"""
    old_db = project_root / "data/chroma_db/memory.db"
    
    if not old_db.exists():
        logger.error(f"❌ 旧数据库不存在: {old_db}")
        raise FileNotFoundError(f"数据库不存在: {old_db}")
    
    conn = sqlite3.connect(str(old_db))
    cursor = conn.cursor()
    
    # 总记录数
    cursor.execute('SELECT COUNT(*) FROM memories')
    total = cursor.fetchone()[0]
    
    # 用户数
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM memories')
    user_count = cursor.fetchone()[0]
    
    # 按类型统计
    cursor.execute('SELECT role, COUNT(*) FROM memories GROUP BY role')
    by_role = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 检查是否有群聊数据（通过检测是否有 group_id 相关字段或数据）
    cursor.execute('PRAGMA table_info(memories)')
    columns = [row[1] for row in cursor.fetchall()]
    has_group_field = 'group_id' in columns or 'scene_id' in columns
    
    conn.close()
    
    return {
        'total': total,
        'user_count': user_count,
        'by_role': by_role,
        'has_group_field': has_group_field
    }


def create_private_db(user_dir: Path):
    """创建用户私聊数据库"""
    db_path = user_dir / "private.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 私聊记忆表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS private_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            query TEXT,
            reply TEXT,
            timestamp INTEGER NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON private_memories(timestamp)")
    
    # 群聊记忆表（该用户在各个群的发言）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            query TEXT,
            reply TEXT,
            timestamp INTEGER NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_timestamp ON group_memories(group_id, timestamp)")
    
    conn.commit()
    conn.close()


def create_user_groups_db(user_dir: Path):
    """创建用户群聊数据库（已废弃，群聊记忆现在存在 private.db 的 group_memories 表中）"""
    # 这个函数保留以兼容旧代码，但不再创建独立的 groups.db
    pass


def create_group_members_db(group_dir: Path):
    """创建群成员数据库"""
    db_path = group_dir / "members.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            sender_name TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            query TEXT,
            reply TEXT,
            timestamp INTEGER NOT NULL
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_timestamp ON member_memories(user_id, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON member_memories(timestamp)")
    conn.commit()
    conn.close()


def migrate_data():
    """迁移数据"""
    old_db = project_root / "data/chroma_db/memory.db"
    new_base = project_root / "data/memory_v2"
    
    logger.info("\n🔄 开始迁移数据...")
    
    # 连接旧数据库
    old_conn = sqlite3.connect(str(old_db))
    old_cursor = old_conn.cursor()
    
    # 获取所有记录
    old_cursor.execute("""
        SELECT id, user_id, role, content, timestamp, query, reply
        FROM memories
        ORDER BY user_id, timestamp
    """)
    
    records = old_cursor.fetchall()
    logger.info(f"  总记录数: {len(records)}")
    
    # 按用户分组
    user_records = defaultdict(list)
    for record in records:
        record_id, user_id, role, content, timestamp, query, reply = record
        user_records[user_id].append({
            'id': record_id,
            'role': role,
            'content': content,
            'timestamp': timestamp,
            'query': query,
            'reply': reply
        })
    
    logger.info(f"  用户数: {len(user_records)}")
    
    # 为每个用户创建私聊数据库
    migrated_users = 0
    migrated_records = 0
    
    for user_id, user_data in user_records.items():
        user_dir = new_base / "private" / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建私聊数据库
        create_private_db(user_dir)
        
        # 插入数据（目前所有数据都当作私聊）
        private_db = user_dir / "private.db"
        conn = sqlite3.connect(str(private_db))
        cursor = conn.cursor()
        
        for record in user_data:
            cursor.execute("""
                INSERT INTO private_memories (role, content, query, reply, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                record['role'],
                record['content'],
                record['query'],
                record['reply'],
                record['timestamp']
            ))
            migrated_records += 1
        
        conn.commit()
        conn.close()
        
        migrated_users += 1
        
        if migrated_users % 10 == 0:
            logger.info(f"  进度: {migrated_users}/{len(user_records)} 用户")
    
    old_conn.close()
    
    logger.info(f"\n✅ 数据迁移完成:")
    logger.info(f"  迁移用户: {migrated_users}")
    logger.info(f"  迁移记录: {migrated_records}")
    
    return migrated_users, migrated_records


def rebuild_faiss_indices():
    """重建 FAISS 索引"""
    logger.info("\n🔨 开始重建 FAISS 索引...")
    logger.info("⚠️ 这需要调用 embedding API，可能需要较长时间...")
    
    try:
        import faiss
        import numpy as np
    except ImportError:
        logger.error("❌ 需要安装 faiss-cpu: pip install faiss-cpu")
        return False
    
    # 加载配置
    from src.core.config_manager import ConfigManager
    ConfigManager.load()
    
    from src.services.vector_service import EmbeddingClient
    embedding_client = EmbeddingClient()
    
    new_base = project_root / "data/memory_v2"
    private_dir = new_base / "private"
    
    if not private_dir.exists():
        logger.error("❌ 私聊数据目录不存在")
        return False
    
    # 为每个用户重建索引
    user_dirs = [d for d in private_dir.iterdir() if d.is_dir()]
    logger.info(f"  找到 {len(user_dirs)} 个用户目录")
    
    success_count = 0
    error_count = 0
    
    for i, user_dir in enumerate(user_dirs, 1):
        user_id = user_dir.name
        private_db = user_dir / "private.db"
        
        if not private_db.exists():
            logger.warning(f"  ⚠️ 用户 {user_id} 的数据库不存在，跳过")
            continue
        
        try:
            # 读取私聊数据
            conn = sqlite3.connect(str(private_db))
            cursor = conn.cursor()
            cursor.execute("SELECT id, content FROM private_memories ORDER BY id")
            records = cursor.fetchall()
            conn.close()
            
            if not records:
                logger.debug(f"  用户 {user_id}: 无数据，跳过")
                continue
            
            # 创建 FAISS 索引
            vector_dim = embedding_client.vector_dim
            index = faiss.IndexFlatIP(vector_dim)
            id_map = []
            
            for record_id, content in records:
                try:
                    # 生成向量
                    embedding = embedding_client.get_embedding(content)
                    
                    # 归一化
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                    
                    # 添加到索引
                    index.add(embedding.reshape(1, -1))
                    id_map.append(record_id)
                
                except Exception as e:
                    logger.error(f"  处理记录 {record_id} 失败: {e}")
                    error_count += 1
            
            # 保存索引
            faiss_path = user_dir / "private.faiss"
            id_map_path = user_dir / "private_id_map.pkl"
            
            faiss.write_index(index, str(faiss_path))
            with open(id_map_path, 'wb') as f:
                pickle.dump(id_map, f)
            
            success_count += 1
            
            if i % 10 == 0:
                logger.info(f"  进度: {i}/{len(user_dirs)} 用户")
        
        except Exception as e:
            logger.error(f"  用户 {user_id} 索引重建失败: {e}")
            error_count += 1
    
    logger.info(f"\n✅ FAISS 索引重建完成:")
    logger.info(f"  成功: {success_count} 个用户")
    logger.info(f"  失败: {error_count} 个")
    
    return True


def verify_migration():
    """验证迁移结果"""
    logger.info("\n🔍 验证迁移结果...")
    
    new_base = project_root / "data/memory_v2"
    private_dir = new_base / "private"
    
    if not private_dir.exists():
        logger.error("❌ 新数据目录不存在")
        return False
    
    # 统计新数据库
    user_dirs = [d for d in private_dir.iterdir() if d.is_dir()]
    total_records = 0
    total_users = len(user_dirs)
    users_with_index = 0
    
    for user_dir in user_dirs:
        private_db = user_dir / "private.db"
        private_faiss = user_dir / "private.faiss"
        
        if private_db.exists():
            conn = sqlite3.connect(str(private_db))
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM private_memories")
                count = cursor.fetchone()[0]
                total_records += count
            except sqlite3.OperationalError:
                # 表可能还不存在
                pass
            conn.close()
        
        if private_faiss.exists():
            users_with_index += 1
    
    logger.info(f"  新数据库统计:")
    logger.info(f"    用户数: {total_users}")
    logger.info(f"    总记录数: {total_records}")
    logger.info(f"    有索引的用户: {users_with_index}/{total_users}")
    
    # 对比旧数据库
    old_db = project_root / "data/chroma_db/memory.db"
    if old_db.exists():
        conn = sqlite3.connect(str(old_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories")
        old_total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM memories")
        old_users = cursor.fetchone()[0]
        conn.close()
        
        logger.info(f"\n  对比旧数据库:")
        logger.info(f"    旧用户数: {old_users} → 新用户数: {total_users}")
        logger.info(f"    旧记录数: {old_total} → 新记录数: {total_records}")
        
        if total_users == old_users and total_records == old_total:
            logger.info(f"  ✅ 数据完整性验证通过")
            return True
        else:
            logger.warning(f"  ⚠️ 数据数量不匹配")
            return False
    
    return True


def update_config():
    """更新配置文件"""
    logger.info("\n📝 更新配置...")
    
    config_path = project_root / "configs/bot_config.toml"
    if not config_path.exists():
        logger.warning("  ⚠️ 配置文件不存在，跳过")
        return
    
    # 读取配置
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否需要更新
    if 'memory_v2' in content:
        logger.info("  配置已经是新版本，跳过")
        return
    
    # 备份配置
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.parent / f"bot_config_backup_{timestamp}.toml"
    shutil.copy2(config_path, backup_path)
    logger.info(f"  配置已备份: {backup_path}")
    
    # 更新路径
    content = content.replace(
        'vector_db_path = "./data/chroma_db"',
        'vector_db_path = "./data/memory_v2"'
    )
    
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("  ✅ 配置已更新")


def main():
    """主函数"""
    print("=" * 70)
    print("记忆系统迁移工具 - 迁移到新的双数据库结构")
    print("=" * 70)
    
    # 1. 分析旧数据库
    print("\n[1/7] 分析旧数据库...")
    stats = analyze_old_database()
    print(f"  总记录数: {stats['total']}")
    print(f"  用户数: {stats['user_count']}")
    print(f"  记忆类型: {stats['by_role']}")
    
    # 2. 确认操作
    print("\n[2/7] 迁移计划:")
    print("  ✓ 备份旧数据库")
    print("  ✓ 创建新的双数据库结构")
    print("  ✓ 迁移所有记忆数据")
    print("  ✓ 重建 FAISS 索引（需要调用 API）")
    print("  ✓ 验证数据完整性")
    print("  ✓ 更新配置文件")
    
    print("\n⚠️ 注意:")
    print("  - 重建索引需要调用 embedding API，可能需要 10-30 分钟")
    print("  - 旧数据库会被备份，不会删除")
    print("  - 可以随时回滚到旧版本")
    
    confirm = input("\n是否继续? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("操作已取消")
        return
    
    # 3. 备份
    print("\n[3/7] 备份旧数据...")
    if not backup_old_database():
        print("❌ 备份失败")
        return
    
    # 4. 迁移数据
    print("\n[4/7] 迁移数据...")
    try:
        users, records = migrate_data()
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}", exc_info=True)
        return
    
    # 5. 重建索引
    print("\n[5/7] 重建 FAISS 索引...")
    rebuild = input("是否重建索引? (yes/no, 建议选 yes): ").strip().lower()
    if rebuild in ['yes', 'y']:
        try:
            rebuild_faiss_indices()
        except Exception as e:
            logger.error(f"❌ 索引重建失败: {e}", exc_info=True)
            print("⚠️ 可以稍后手动运行: python tools/rebuild_faiss_indices.py")
    else:
        print("  跳过索引重建（可稍后手动执行）")
    
    # 6. 验证
    print("\n[6/7] 验证迁移...")
    verify_migration()
    
    # 7. 更新配置
    print("\n[7/7] 更新配置...")
    update_config()
    
    # 完成
    print("\n" + "=" * 70)
    print("✅ 迁移完成！")
    print("=" * 70)
    
    print("\n📋 迁移摘要:")
    print(f"  迁移用户: {users}")
    print(f"  迁移记录: {records}")
    print(f"  新数据位置: data/memory_v2/")
    print(f"  旧数据备份: data/backup_*/")
    
    print("\n🔧 下一步:")
    print("  1. 重启 Bot: python bot.py")
    print("  2. 测试私聊和群聊功能")
    print("  3. 如有问题，可从备份恢复")
    
    print("\n💡 提示:")
    print("  - 新系统支持跨群组检索")
    print("  - 私聊和群聊记忆完全隔离")
    print("  - 每个用户/群都有独立的索引")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已中断")
    except Exception as e:
        logger.error(f"❌ 发生错误: {e}", exc_info=True)
