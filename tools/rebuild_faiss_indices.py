"""
重建 FAISS 索引工具

用于为新的双数据库结构重建 FAISS 索引
可以单独运行，也可以在迁移后补充运行
"""
import sqlite3
import pickle
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.logger import logger


def rebuild_user_private_index(user_dir: Path, embedding_client, faiss, np):
    """重建用户私聊索引"""
    user_id = user_dir.name
    private_db = user_dir / "private.db"
    
    if not private_db.exists():
        return False, "数据库不存在"
    
    # 读取数据
    conn = sqlite3.connect(str(private_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM private_memories ORDER BY id")
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return False, "无数据"
    
    # 创建索引
    vector_dim = embedding_client.vector_dim
    index = faiss.IndexFlatIP(vector_dim)
    id_map = []
    
    success = 0
    errors = 0
    
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
            success += 1
        
        except Exception as e:
            logger.debug(f"  记录 {record_id} 失败: {e}")
            errors += 1
    
    # 保存索引
    faiss_path = user_dir / "private.faiss"
    id_map_path = user_dir / "private_id_map.pkl"
    
    faiss.write_index(index, str(faiss_path))
    with open(id_map_path, 'wb') as f:
        pickle.dump(id_map, f)
    
    return True, f"{success} 条记录, {errors} 个错误"


def rebuild_user_groups_index(user_dir: Path, embedding_client, faiss, np):
    """重建用户群聊索引"""
    groups_db = user_dir / "groups.db"
    
    if not groups_db.exists():
        return False, "数据库不存在"
    
    # 读取数据
    conn = sqlite3.connect(str(groups_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM group_memories ORDER BY id")
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return False, "无数据"
    
    # 创建索引
    vector_dim = embedding_client.vector_dim
    index = faiss.IndexFlatIP(vector_dim)
    id_map = []
    
    success = 0
    errors = 0
    
    for record_id, content in records:
        try:
            embedding = embedding_client.get_embedding(content)
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            index.add(embedding.reshape(1, -1))
            id_map.append(record_id)
            success += 1
        except Exception as e:
            logger.debug(f"  记录 {record_id} 失败: {e}")
            errors += 1
    
    # 保存索引
    faiss_path = user_dir / "groups.faiss"
    id_map_path = user_dir / "groups_id_map.pkl"
    
    faiss.write_index(index, str(faiss_path))
    with open(id_map_path, 'wb') as f:
        pickle.dump(id_map, f)
    
    return True, f"{success} 条记录, {errors} 个错误"


def rebuild_group_members_index(group_dir: Path, embedding_client, faiss, np):
    """重建群成员索引"""
    group_id = group_dir.name
    members_db = group_dir / "members.db"
    
    if not members_db.exists():
        return False, "数据库不存在"
    
    # 读取数据
    conn = sqlite3.connect(str(members_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM member_memories ORDER BY id")
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return False, "无数据"
    
    # 创建索引
    vector_dim = embedding_client.vector_dim
    index = faiss.IndexFlatIP(vector_dim)
    id_map = []
    
    success = 0
    errors = 0
    
    for record_id, content in records:
        try:
            embedding = embedding_client.get_embedding(content)
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            index.add(embedding.reshape(1, -1))
            id_map.append(record_id)
            success += 1
        except Exception as e:
            logger.debug(f"  记录 {record_id} 失败: {e}")
            errors += 1
    
    # 保存索引
    faiss_path = group_dir / "members.faiss"
    id_map_path = group_dir / "members_id_map.pkl"
    
    faiss.write_index(index, str(faiss_path))
    with open(id_map_path, 'wb') as f:
        pickle.dump(id_map, f)
    
    return True, f"{success} 条记录, {errors} 个错误"


def main():
    """主函数"""
    print("=" * 70)
    print("FAISS 索引重建工具")
    print("=" * 70)
    
    # 检查依赖
    try:
        import faiss
        import numpy as np
    except ImportError:
        logger.error("❌ 需要安装 faiss-cpu: pip install faiss-cpu")
        return
    
    # 加载配置
    from src.core.config_manager import ConfigManager
    ConfigManager.load()
    
    from src.services.vector_service import EmbeddingClient
    embedding_client = EmbeddingClient()
    
    logger.info(f"✅ Embedding 客户端初始化成功")
    logger.info(f"   模型: {embedding_client.model}")
    logger.info(f"   维度: {embedding_client.vector_dim}")
    
    # 检查数据目录
    base_dir = Path("data/memory_v2")
    if not base_dir.exists():
        logger.error(f"❌ 数据目录不存在: {base_dir}")
        logger.info("   请先运行迁移工具: python tools/migrate_to_new_memory_system.py")
        return
    
    # 选择重建范围
    print("\n请选择重建范围:")
    print("  1. 重建所有索引（私聊 + 群聊）")
    print("  2. 只重建私聊索引")
    print("  3. 只重建群聊索引")
    print("  4. 重建指定用户的索引")
    
    choice = input("\n请输入选项 (1-4): ").strip()
    
    if choice == "1":
        # 重建所有索引
        print("\n🔨 重建所有索引...")
        
        # 私聊索引
        private_dir = base_dir / "private"
        if private_dir.exists():
            user_dirs = [d for d in private_dir.iterdir() if d.is_dir()]
            logger.info(f"\n📁 私聊索引: {len(user_dirs)} 个用户")
            
            success = 0
            skipped = 0
            errors = 0
            
            for i, user_dir in enumerate(user_dirs, 1):
                user_id = user_dir.name
                
                # 重建私聊索引
                ok, msg = rebuild_user_private_index(user_dir, embedding_client, faiss, np)
                if ok:
                    success += 1
                    logger.debug(f"  [{i}/{len(user_dirs)}] 用户 {user_id}: {msg}")
                elif "无数据" in msg:
                    skipped += 1
                else:
                    errors += 1
                    logger.warning(f"  [{i}/{len(user_dirs)}] 用户 {user_id}: {msg}")
                
                if i % 10 == 0:
                    logger.info(f"  进度: {i}/{len(user_dirs)}")
            
            logger.info(f"\n✅ 私聊索引重建完成: 成功 {success}, 跳过 {skipped}, 失败 {errors}")
        
        # 群聊索引
        groups_dir = base_dir / "groups"
        if groups_dir.exists():
            group_dirs = [d for d in groups_dir.iterdir() if d.is_dir()]
            if group_dirs:
                logger.info(f"\n📁 群聊索引: {len(group_dirs)} 个群")
                
                success = 0
                skipped = 0
                errors = 0
                
                for i, group_dir in enumerate(group_dirs, 1):
                    group_id = group_dir.name
                    
                    ok, msg = rebuild_group_members_index(group_dir, embedding_client, faiss, np)
                    if ok:
                        success += 1
                        logger.debug(f"  [{i}/{len(group_dirs)}] 群 {group_id}: {msg}")
                    elif "无数据" in msg:
                        skipped += 1
                    else:
                        errors += 1
                        logger.warning(f"  [{i}/{len(group_dirs)}] 群 {group_id}: {msg}")
                    
                    if i % 5 == 0:
                        logger.info(f"  进度: {i}/{len(group_dirs)}")
                
                logger.info(f"\n✅ 群聊索引重建完成: 成功 {success}, 跳过 {skipped}, 失败 {errors}")
            else:
                logger.info("\n📁 群聊索引: 无群聊数据")
    
    elif choice == "2":
        # 只重建私聊索引
        print("\n🔨 重建私聊索引...")
        private_dir = base_dir / "private"
        
        if not private_dir.exists():
            logger.error("❌ 私聊数据目录不存在")
            return
        
        user_dirs = [d for d in private_dir.iterdir() if d.is_dir()]
        logger.info(f"找到 {len(user_dirs)} 个用户")
        
        success = 0
        skipped = 0
        errors = 0
        
        for i, user_dir in enumerate(user_dirs, 1):
            user_id = user_dir.name
            
            ok, msg = rebuild_user_private_index(user_dir, embedding_client, faiss, np)
            if ok:
                success += 1
            elif "无数据" in msg:
                skipped += 1
            else:
                errors += 1
            
            if i % 10 == 0:
                logger.info(f"  进度: {i}/{len(user_dirs)}")
        
        logger.info(f"\n✅ 完成: 成功 {success}, 跳过 {skipped}, 失败 {errors}")
    
    elif choice == "3":
        # 只重建群聊索引
        print("\n🔨 重建群聊索引...")
        groups_dir = base_dir / "groups"
        
        if not groups_dir.exists():
            logger.error("❌ 群聊数据目录不存在")
            return
        
        group_dirs = [d for d in groups_dir.iterdir() if d.is_dir()]
        logger.info(f"找到 {len(group_dirs)} 个群")
        
        success = 0
        skipped = 0
        errors = 0
        
        for i, group_dir in enumerate(group_dirs, 1):
            group_id = group_dir.name
            
            ok, msg = rebuild_group_members_index(group_dir, embedding_client, faiss, np)
            if ok:
                success += 1
            elif "无数据" in msg:
                skipped += 1
            else:
                errors += 1
            
            if i % 5 == 0:
                logger.info(f"  进度: {i}/{len(group_dirs)}")
        
        logger.info(f"\n✅ 完成: 成功 {success}, 跳过 {skipped}, 失败 {errors}")
    
    elif choice == "4":
        # 重建指定用户
        user_id = input("\n请输入用户 ID: ").strip()
        user_dir = base_dir / "private" / user_id
        
        if not user_dir.exists():
            logger.error(f"❌ 用户目录不存在: {user_dir}")
            return
        
        print(f"\n🔨 重建用户 {user_id} 的索引...")
        
        # 私聊索引
        ok, msg = rebuild_user_private_index(user_dir, embedding_client, faiss, np)
        if ok:
            logger.info(f"  ✅ 私聊索引: {msg}")
        else:
            logger.warning(f"  ⚠️ 私聊索引: {msg}")
        
        # 群聊索引
        ok, msg = rebuild_user_groups_index(user_dir, embedding_client, faiss, np)
        if ok:
            logger.info(f"  ✅ 群聊索引: {msg}")
        else:
            logger.warning(f"  ⚠️ 群聊索引: {msg}")
    
    else:
        print("无效选项")
        return
    
    print("\n" + "=" * 70)
    print("✅ 索引重建完成！")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已中断")
    except Exception as e:
        logger.error(f"❌ 发生错误: {e}", exc_info=True)
