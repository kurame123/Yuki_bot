"""
一键重建知识库
1. 删除旧的知识库文件
2. 清洗原始文本
3. 构建向量数据库
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.logger import logger


def delete_old_knowledge_base():
    """删除旧的知识库文件"""
    print("🗑️  步骤 0/3: 删除旧知识库")
    print("-" * 60)
    
    files_to_delete = [
        Path("data/chroma_db/knowledge.db"),
        Path("data/chroma_db/knowledge.faiss"),
        Path("data/chroma_db/kb_id_map.pkl"),
        Path("data/cleaned_knowledge.json"),
    ]
    
    deleted_count = 0
    for file_path in files_to_delete:
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"✅ 已删除: {file_path}")
                deleted_count += 1
            except Exception as e:
                logger.warning(f"⚠️  删除失败 {file_path}: {e}")
        else:
            logger.debug(f"   跳过（不存在）: {file_path}")
    
    if deleted_count > 0:
        logger.info(f"✅ 共删除 {deleted_count} 个旧文件")
    else:
        logger.info("✅ 无旧文件需要删除")
    
    print()


async def main():
    """主流程"""
    print("\n" + "="*60)
    print("🔄 一键重建知识库")
    print("="*60 + "\n")
    
    # 步骤0：询问是否删除旧文件
    print("⚠️  是否删除旧知识库文件？")
    print("   [Y] 是（删除旧数据，全新构建）")
    print("   [N] 否（保留旧数据）")
    choice = input("\n请选择 (Y/N): ").strip().upper()
    
    if choice == 'Y':
        print()
        delete_old_knowledge_base()
        print("="*60 + "\n")
    else:
        print("✅ 跳过删除步骤\n")
        print("="*60 + "\n")
    
    # 步骤1：询问是否清洗文本
    print("📝 步骤 1/2: 清洗原始文本")
    print("-" * 60)
    print("⚠️  是否执行文本清洗？")
    print("   [Y] 是（使用 LLM 清洗 knowledge_docs/ 下的文本）")
    print("   [N] 否（跳过，使用已有的 cleaned_knowledge.json）")
    choice = input("\n请选择 (Y/N): ").strip().upper()
    
    if choice == 'Y':
        print()
        try:
            from tools.kb_cleaner import process_knowledge_files
            await process_knowledge_files()
        except Exception as e:
            logger.error(f"清洗失败: {e}")
            return
    else:
        print("✅ 跳过清洗步骤")
        # 检查是否存在清洗后的文件
        json_file = Path("data/cleaned_knowledge.json")
        if not json_file.exists():
            print("❌ 错误：找不到 cleaned_knowledge.json")
            print("   请先执行清洗步骤或手动创建该文件")
            return
        print(f"✅ 将使用现有文件: {json_file}")
    
    print("\n" + "="*60 + "\n")
    
    # 步骤2：询问是否构建向量库
    print("📚 步骤 2/2: 构建向量数据库")
    print("-" * 60)
    print("⚠️  是否构建向量数据库？")
    print("   [Y] 是（从 cleaned_knowledge.json 构建）")
    print("   [N] 否（跳过）")
    choice = input("\n请选择 (Y/N): ").strip().upper()
    
    if choice == 'Y':
        print()
        try:
            from tools.kb_builder.build_kb import FAISSKBBuilder
            builder = FAISSKBBuilder()
            builder.run(clear_old=False, use_cleaned=True)  # 不再自动清空，由用户在步骤0决定
        except Exception as e:
            logger.error(f"构建失败: {e}")
            return
    else:
        print("✅ 跳过构建步骤")
    
    print("\n" + "="*60)
    print("✅ 操作完成！")
    print("="*60)
    print("\n💡 提示：")
    print("   - 重启 bot 后生效")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
