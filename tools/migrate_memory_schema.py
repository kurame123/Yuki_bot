"""
记忆数据库结构迁移工具

从当前的单维度（user_id）迁移到双维度（user_id + scene_id）
"""
import sqlite3
import shutil
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.logger import logger


def backup_database(db_path: Path) -> Path:
    """备份数据库"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_before_migration_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"✅ 数据库已备份: {backup_path}")
    return backup_path


def analyze_current_schema(db_path: Path):
    """分析当前数据库结构"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 获取表结构
    cursor.execute('PRAGMA table_info(memories)')
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    # 统计数据
    cursor.execute('SELECT COUNT(*) FROM memories')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM memories')
    user_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'columns': columns,
        'total': total,
        'user_count': user_count
    }


def check_if_migrated(db_path: Path) -> bool:
    """检查是否已经迁移过"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute('PRAGMA table_info(memories)')
    columns = [row[1] for row in cursor.fetchall()]
    
    conn.close()
    
    return 'scene_type' in columns and 'scene_id' in columns


def migrate_schema(db_path: Path):
    """迁移数据库结构"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    logger.info("开始迁移数据库结构...")
    
    # 1. 添加新字段
    logger.info("  [1/5] 添加 scene_type 字段...")
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN scene_type TEXT DEFAULT 'private'")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            logger.info("    字段已存在，跳过")
        else:
            raise
    
    logger.info("  [2/5] 添加 scene_id 字段...")
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN scene_id TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            logger.info("    字段已存在，跳过")
        else:
            raise
    
    # 2. 迁移现有数据（私聊记忆：scene_id = user_id）
    logger.info("  [3/5] 迁移现有数据...")
    cursor.execute("""
        UPDATE memories 
        SET scene_id = user_id, scene_type = 'private'
        WHERE scene_id IS NULL
    """)
    affected = cursor.rowcount
    conn.commit()
    logger.info(f"    已更新 {affected} 条记录")
    
    # 3. 创建索引
    logger.info("  [4/5] 创建索引...")
    
    # 检查索引是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_user_scene'")
    if not cursor.fetchone():
        cursor.execute("CREATE INDEX idx_user_scene ON memories(user_id, scene_id, timestamp)")
        logger.info("    ✓ 创建 idx_user_scene")
    else:
        logger.info("    idx_user_scene 已存在")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_scene'")
    if not cursor.fetchone():
        cursor.execute("CREATE INDEX idx_scene ON memories(scene_id, timestamp)")
        logger.info("    ✓ 创建 idx_scene")
    else:
        logger.info("    idx_scene 已存在")
    
    conn.commit()
    
    # 4. 验证迁移
    logger.info("  [5/5] 验证迁移...")
    cursor.execute("SELECT COUNT(*) FROM memories WHERE scene_id IS NULL")
    null_count = cursor.fetchone()[0]
    
    if null_count > 0:
        logger.warning(f"    ⚠️ 仍有 {null_count} 条记录的 scene_id 为空")
    else:
        logger.info("    ✓ 所有记录都有 scene_id")
    
    # 统计迁移结果
    cursor.execute("SELECT scene_type, COUNT(*) FROM memories GROUP BY scene_type")
    stats = {row[0]: row[1] for row in cursor.fetchall()}
    
    logger.info("\n迁移结果统计:")
    for scene_type, count in stats.items():
        logger.info(f"  {scene_type}: {count} 条")
    
    conn.close()
    logger.info("\n✅ 数据库结构迁移完成！")


def verify_migration(db_path: Path):
    """验证迁移结果"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    logger.info("\n=== 迁移验证 ===")
    
    # 1. 检查字段
    cursor.execute('PRAGMA table_info(memories)')
    columns = [row[1] for row in cursor.fetchall()]
    
    required_columns = ['scene_type', 'scene_id']
    missing = [col for col in required_columns if col not in columns]
    
    if missing:
        logger.error(f"❌ 缺少字段: {missing}")
        return False
    else:
        logger.info("✅ 所有必需字段都存在")
    
    # 2. 检查索引
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='memories'")
    indices = [row[0] for row in cursor.fetchall()]
    
    required_indices = ['idx_user_scene', 'idx_scene']
    missing_indices = [idx for idx in required_indices if idx not in indices]
    
    if missing_indices:
        logger.warning(f"⚠️ 缺少索引: {missing_indices}")
    else:
        logger.info("✅ 所有索引都已创建")
    
    # 3. 检查数据完整性
    cursor.execute("SELECT COUNT(*) FROM memories WHERE scene_id IS NULL")
    null_count = cursor.fetchone()[0]
    
    if null_count > 0:
        logger.error(f"❌ 有 {null_count} 条记录的 scene_id 为空")
        return False
    else:
        logger.info("✅ 所有记录都有 scene_id")
    
    # 4. 显示示例数据
    cursor.execute("""
        SELECT user_id, scene_type, scene_id, role, 
               substr(content, 1, 50) as content_preview
        FROM memories 
        LIMIT 5
    """)
    
    logger.info("\n示例数据:")
    for row in cursor.fetchall():
        logger.info(f"  用户{row[0]} | {row[1]} | 场景{row[2]} | {row[3]} | {row[4]}...")
    
    conn.close()
    
    logger.info("\n✅ 迁移验证通过！")
    return True


def main():
    """主函数"""
    print("=" * 60)
    print("记忆数据库结构迁移工具")
    print("=" * 60)
    
    db_path = Path("data/chroma_db/memory.db")
    
    if not db_path.exists():
        logger.error(f"❌ 数据库不存在: {db_path}")
        return
    
    # 1. 分析当前结构
    print("\n[1/4] 分析当前数据库...")
    current = analyze_current_schema(db_path)
    print(f"  总记录数: {current['total']}")
    print(f"  用户数: {current['user_count']}")
    print(f"  当前字段: {', '.join(current['columns'].keys())}")
    
    # 2. 检查是否已迁移
    if check_if_migrated(db_path):
        print("\n⚠️ 数据库已经迁移过，是否重新迁移？")
        confirm = input("输入 'yes' 继续: ").strip().lower()
        if confirm != 'yes':
            print("操作已取消")
            return
    
    # 3. 确认操作
    print("\n[2/4] 准备执行迁移:")
    print("  - 添加 scene_type 字段（场景类型）")
    print("  - 添加 scene_id 字段（场景ID）")
    print("  - 迁移现有数据（设置为私聊）")
    print("  - 创建新索引")
    
    confirm = input("\n是否继续? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("操作已取消")
        return
    
    # 4. 备份
    print("\n[3/4] 备份数据库...")
    backup_path = backup_database(db_path)
    print(f"  备份位置: {backup_path}")
    
    # 5. 执行迁移
    print("\n[4/4] 执行迁移...")
    try:
        migrate_schema(db_path)
        
        # 6. 验证
        if verify_migration(db_path):
            print("\n" + "=" * 60)
            print("✅ 迁移成功完成！")
            print("=" * 60)
            print("\n下一步:")
            print("1. 运行 'python tools/rebuild_memory_index.py' 重建 FAISS 索引")
            print("2. 更新代码以支持场景维度检索")
            print("3. 测试私聊和群聊功能")
        else:
            print("\n❌ 迁移验证失败，请检查日志")
            print(f"可以从备份恢复: {backup_path}")
    
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}", exc_info=True)
        print(f"\n可以从备份恢复: {backup_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已中断")
    except Exception as e:
        logger.error(f"❌ 发生错误: {e}", exc_info=True)
