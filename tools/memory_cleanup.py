"""
记忆数据库清理和修复工具

功能:
1. 备份当前数据库
2. 删除 legacy 数据
3. 重建 FAISS 索引
4. 验证数据一致性
"""
import sqlite3
import pickle
import shutil
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.logger import logger
from src.core.config_manager import ConfigManager


def backup_database(db_path: Path) -> Path:
    """备份数据库"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"✅ 数据库已备份: {backup_path}")
    return backup_path


def backup_faiss_index(faiss_path: Path, id_map_path: Path):
    """备份 FAISS 索引"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if faiss_path.exists():
        backup_faiss = faiss_path.parent / f"{faiss_path.stem}_backup_{timestamp}{faiss_path.suffix}"
        shutil.copy2(faiss_path, backup_faiss)
        logger.info(f"✅ FAISS 索引已备份: {backup_faiss}")
    
    if id_map_path.exists():
        backup_id_map = id_map_path.parent / f"{id_map_path.stem}_backup_{timestamp}{id_map_path.suffix}"
        shutil.copy2(id_map_path, backup_id_map)
        logger.info(f"✅ ID 映射已备份: {backup_id_map}")


def analyze_database(db_path: Path):
    """分析数据库状态"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 总记录数
    cursor.execute('SELECT COUNT(*) FROM memories')
    total = cursor.fetchone()[0]
    
    # 按类型统计
    cursor.execute('SELECT role, COUNT(*) FROM memories GROUP BY role')
    by_role = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 用户数
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM memories')
    user_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total,
        'by_role': by_role,
        'user_count': user_count
    }


def clean_legacy_data(db_path: Path) -> int:
    """删除 legacy 数据"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 统计要删除的数量
    cursor.execute("SELECT COUNT(*) FROM memories WHERE role = 'legacy'")
    legacy_count = cursor.fetchone()[0]
    
    if legacy_count == 0:
        logger.info("没有 legacy 数据需要清理")
        conn.close()
        return 0
    
    # 删除 legacy 数据
    cursor.execute("DELETE FROM memories WHERE role = 'legacy'")
    conn.commit()
    
    # 优化数据库（回收空间）
    cursor.execute("VACUUM")
    conn.commit()
    
    conn.close()
    
    logger.info(f"✅ 已删除 {legacy_count} 条 legacy 数据")
    return legacy_count


def rebuild_faiss_index(db_path: Path, faiss_path: Path, id_map_path: Path):
    """重建 FAISS 索引"""
    try:
        import faiss
        import numpy as np
    except ImportError:
        logger.error("❌ 需要安装 faiss-cpu: pip install faiss-cpu")
        return False
    
    # 加载配置
    ConfigManager.load()
    
    # 初始化嵌入客户端
    from src.services.vector_service import EmbeddingClient
    embedding_client = EmbeddingClient()
    
    # 连接数据库
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 获取所有记录
    cursor.execute("SELECT id, content FROM memories ORDER BY id")
    records = cursor.fetchall()
    
    if not records:
        logger.warning("数据库为空，跳过索引重建")
        conn.close()
        return True
    
    logger.info(f"开始重建索引，共 {len(records)} 条记录...")
    
    # 创建新索引
    vector_dim = embedding_client.vector_dim
    index = faiss.IndexFlatIP(vector_dim)
    id_map = []
    
    # 批量处理
    batch_size = 10
    success_count = 0
    error_count = 0
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        
        for record_id, content in batch:
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
                success_count += 1
                
            except Exception as e:
                logger.error(f"处理记录 {record_id} 失败: {e}")
                error_count += 1
        
        # 进度提示
        if (i + batch_size) % 100 == 0:
            logger.info(f"  进度: {min(i + batch_size, len(records))}/{len(records)}")
    
    conn.close()
    
    # 保存索引
    faiss.write_index(index, str(faiss_path))
    with open(id_map_path, 'wb') as f:
        pickle.dump(id_map, f)
    
    logger.info(f"✅ 索引重建完成: 成功 {success_count} 条, 失败 {error_count} 条")
    logger.info(f"   FAISS 索引: {faiss_path}")
    logger.info(f"   ID 映射: {id_map_path}")
    
    return True


def verify_consistency(db_path: Path, faiss_path: Path, id_map_path: Path):
    """验证数据一致性"""
    try:
        import faiss
    except ImportError:
        logger.error("❌ 需要安装 faiss-cpu")
        return False
    
    # SQLite 记录数
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM memories')
    db_count = cursor.fetchone()[0]
    conn.close()
    
    # FAISS 向量数
    index = faiss.read_index(str(faiss_path))
    faiss_count = index.ntotal
    
    # ID 映射数
    with open(id_map_path, 'rb') as f:
        id_map = pickle.load(f)
    id_map_count = len(id_map)
    
    logger.info("\n=== 数据一致性验证 ===")
    logger.info(f"SQLite 记录数: {db_count}")
    logger.info(f"FAISS 向量数: {faiss_count}")
    logger.info(f"ID 映射数量: {id_map_count}")
    
    if db_count == faiss_count == id_map_count:
        logger.info("✅ 数据完全一致")
        return True
    else:
        logger.warning("⚠️ 数据不一致")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("记忆数据库清理和修复工具")
    print("=" * 60)
    
    # 数据库路径
    db_path = Path("data/chroma_db/memory.db")
    faiss_path = Path("data/chroma_db/memory.faiss")
    id_map_path = Path("data/chroma_db/memory_id_map.pkl")
    
    if not db_path.exists():
        logger.error(f"❌ 数据库不存在: {db_path}")
        return
    
    # 1. 分析当前状态
    print("\n[1/6] 分析当前数据库状态...")
    before_stats = analyze_database(db_path)
    print(f"  总记录数: {before_stats['total']}")
    print(f"  用户数: {before_stats['user_count']}")
    print(f"  记忆类型分布:")
    for role, count in before_stats['by_role'].items():
        print(f"    {role}: {count} 条")
    
    # 2. 确认操作
    print("\n[2/6] 准备执行以下操作:")
    print("  - 备份数据库和索引")
    print("  - 删除所有 legacy 数据")
    print("  - 重建 FAISS 索引")
    print("  - 验证数据一致性")
    
    confirm = input("\n是否继续? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("操作已取消")
        return
    
    # 3. 备份
    print("\n[3/6] 备份数据...")
    backup_database(db_path)
    backup_faiss_index(faiss_path, id_map_path)
    
    # 4. 清理 legacy 数据
    print("\n[4/6] 清理 legacy 数据...")
    deleted_count = clean_legacy_data(db_path)
    
    # 5. 重建索引
    print("\n[5/6] 重建 FAISS 索引...")
    print("⚠️ 这可能需要几分钟时间，请耐心等待...")
    success = rebuild_faiss_index(db_path, faiss_path, id_map_path)
    
    if not success:
        logger.error("❌ 索引重建失败")
        return
    
    # 6. 验证
    print("\n[6/6] 验证数据一致性...")
    verify_consistency(db_path, faiss_path, id_map_path)
    
    # 最终统计
    print("\n" + "=" * 60)
    print("清理完成！")
    print("=" * 60)
    
    after_stats = analyze_database(db_path)
    print(f"\n清理前: {before_stats['total']} 条记录")
    print(f"清理后: {after_stats['total']} 条记录")
    print(f"删除: {deleted_count} 条")
    print(f"用户数: {after_stats['user_count']}")
    
    print("\n记忆类型分布:")
    for role, count in after_stats['by_role'].items():
        print(f"  {role}: {count} 条")
    
    print("\n✅ 所有操作完成！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已中断")
    except Exception as e:
        logger.error(f"❌ 发生错误: {e}", exc_info=True)
