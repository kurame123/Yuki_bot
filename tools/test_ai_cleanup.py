"""
测试 AI 清理功能

创建测试数据并验证 AI 识别能力
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.core.logger import setup_logger
from src.core.RAGM.graph_storage import GraphStorage
from src.core.RAGM.ai_graph_cleaner import AIGraphCleaner

logger = setup_logger(__name__)


async def test_ai_cleanup():
    """测试 AI 清理功能"""
    # 加载配置
    from src.core.config_manager import ConfigManager
    ConfigManager.load()
    
    # 使用测试数据库
    test_db = str(project_root / "data" / "test_ai_cleanup.db")
    graph = GraphStorage(db_path=test_db)
    cleaner = AIGraphCleaner(graph)
    
    print("\n" + "=" * 60)
    print("AI 图谱清理功能测试")
    print("=" * 60)
    
    test_user = "test_user_ai"
    
    # 1. 创建测试数据
    print("\n步骤 1: 创建测试数据...")
    
    # 正常实体
    graph.add_node(test_user, "小明", "人物")
    graph.add_node(test_user, "小红", "人物")
    graph.add_node(test_user, "北京", "地点")
    graph.add_edge(test_user, "小明", "小红", "喜欢")
    graph.add_edge(test_user, "小明", "北京", "住在")
    
    # 重复实体（语义相似）
    graph.add_node(test_user, "小明同学", "人物")  # 应该和"小明"合并
    graph.add_node(test_user, "北京市", "地点")    # 应该和"北京"合并
    graph.add_edge(test_user, "小红", "小明同学", "认识")
    
    # 无用实体
    graph.add_node(test_user, "这个", "其他")      # 应该删除
    graph.add_node(test_user, "那个", "其他")      # 应该删除
    graph.add_node(test_user, "东西", "物品")      # 应该删除
    graph.add_node(test_user, "不知道", "其他")    # 应该删除
    
    stats = graph.get_user_graph_stats(test_user)
    print(f"✅ 创建完成: {stats['nodes']} 个节点, {stats['edges']} 个关系")
    
    # 2. 测试 AI 识别重复实体
    print("\n步骤 2: 测试 AI 识别重复实体...")
    
    entities = graph.search_entities(test_user, "", limit=100)
    duplicates = await cleaner.identify_duplicate_entities(test_user, entities)
    
    print(f"✅ AI 识别到 {len(duplicates)} 组重复实体:")
    for main, dups in duplicates:
        print(f"   - {main} ← {', '.join(dups)}")
    
    # 3. 测试 AI 识别无用实体
    print("\n步骤 3: 测试 AI 识别无用实体...")
    
    useless = await cleaner.identify_useless_entities(test_user, entities)
    
    print(f"✅ AI 识别到 {len(useless)} 个无用实体:")
    if useless:
        print(f"   - {', '.join(useless)}")
    
    # 4. 执行 AI 清理
    print("\n步骤 4: 执行 AI 清理...")
    
    result = await cleaner.ai_cleanup_user(test_user)
    
    print(f"✅ 清理完成: 合并 {result['merged']} 个, 删除 {result['deleted']} 个")
    
    stats = graph.get_user_graph_stats(test_user)
    print(f"   当前: {stats['nodes']} 个节点, {stats['edges']} 个关系")
    
    # 5. 验证结果
    print("\n步骤 5: 验证清理结果...")
    
    # 验证重复实体已合并
    entities_after = graph.search_entities(test_user, "", limit=100)
    entity_names = [e['entity'] for e in entities_after]
    
    if "小明" in entity_names and "小明同学" not in entity_names:
        print("✅ 重复实体 '小明同学' 已合并到 '小明'")
    else:
        print("❌ 重复实体合并失败")
    
    if "北京" in entity_names and "北京市" not in entity_names:
        print("✅ 重复实体 '北京市' 已合并到 '北京'")
    else:
        print("❌ 重复实体合并失败")
    
    # 验证无用实体已删除
    useless_found = [e for e in entity_names if e in ["这个", "那个", "东西", "不知道"]]
    if not useless_found:
        print("✅ 无用实体已全部删除")
    else:
        print(f"❌ 仍有无用实体: {', '.join(useless_found)}")
    
    # 6. 清理测试数据
    print("\n步骤 6: 清理测试数据...")
    graph.clear_user_graph(test_user)
    print("✅ 测试数据已清理")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60 + "\n")
    
    print("💡 提示:")
    print("   - AI 识别结果取决于 LLM 的能力")
    print("   - 如果识别不准确，可以调整提示词")
    print("   - 建议先小范围测试，再大规模应用")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(test_ai_cleanup())
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)
