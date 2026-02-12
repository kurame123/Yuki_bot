"""
知识库构建工具 - FAISS + SQLite 版本
负责将 knowledge_docs 文件夹中的文本文件切片、向量化并存入数据库

使用方法：
    python tools/kb_builder/build_kb_faiss.py
"""
import sys
import os
import glob
import sqlite3
import numpy as np
import faiss
import pickle
from pathlib import Path

# 路径配置
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.core.config_manager import ConfigManager
from src.services.vector_service import EmbeddingClient


class FAISSKBBuilder:
    """FAISS 知识库构建器"""
    
    def __init__(self):
        """初始化构建器"""
        ConfigManager.load()
        self.config = ConfigManager.get_bot_config()
        self.ai_config = ConfigManager.get_ai_config()
        
        # 数据库路径
        self.db_path = Path(project_root) / self.config.storage.vector_db_path
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.kb_db_path = self.db_path / "knowledge.db"
        self.kb_index_path = self.db_path / "knowledge.faiss"
        self.kb_id_map_path = self.db_path / "kb_id_map.pkl"
        
        self.vector_dim = self.ai_config.embedding.vector_dim
        
        # 初始化嵌入客户端
        self.embedding_client = EmbeddingClient()
        
        print(f"✅ 构建器初始化完成")
        print(f"   数据库路径: {self.kb_db_path}")
        print(f"   索引路径: {self.kb_index_path}")
    
    def split_text(self, text: str, chunk_size: int = 150, overlap: int = 40) -> list:
        """智能文本切片"""
        sentence_endings = ['。', '！', '？', '!', '?', '\n\n']
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            if end < len(text):
                best_end = end
                for marker in sentence_endings:
                    search_start = start + chunk_size // 2
                    last_pos = text.rfind(marker, search_start, end + 10)
                    if last_pos != -1:
                        candidate_end = last_pos + len(marker)
                        if candidate_end > best_end - 20:
                            best_end = candidate_end
                end = best_end
            
            chunk = text[start:end].strip()
            if chunk and len(chunk) >= 10:
                chunks.append(chunk)
            
            if end > start + chunk_size - 10:
                start = end - overlap
            else:
                start = end
        
        return chunks
    
    def clear_knowledge_base(self):
        """清空旧知识库"""
        try:
            print("🗑️  正在清空旧知识库...")
            
            # 删除旧文件
            if self.kb_db_path.exists():
                self.kb_db_path.unlink()
            if self.kb_index_path.exists():
                self.kb_index_path.unlink()
            if self.kb_id_map_path.exists():
                self.kb_id_map_path.unlink()
            
            print("✅ 旧知识库已清空")
        except Exception as e:
            print(f"⚠️  清空知识库时出错: {e}")
    
    def run(self, clear_old: bool = True, use_cleaned: bool = True):
        """
        执行知识库构建
        
        Args:
            clear_old: 是否清空旧知识库
            use_cleaned: 是否使用清洗后的 JSON 数据（推荐）
        """
        # 1. 清空旧知识
        if clear_old:
            self.clear_knowledge_base()
        
        # 2. 初始化数据库
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
        conn.commit()
        
        # 3. 初始化 FAISS 索引
        index = faiss.IndexFlatIP(self.vector_dim)
        id_map = []
        
        # 4. 选择数据源
        if use_cleaned:
            # 使用清洗后的 JSON 数据
            total_chunks = self._build_from_cleaned_json(conn, cursor, index, id_map)
        else:
            # 使用原始 txt 文件
            total_chunks = self._build_from_raw_files(conn, cursor, index, id_map)
        
        # 5. 保存数据
        conn.commit()
        conn.close()
        
        # 保存 FAISS 索引
        faiss.write_index(index, str(self.kb_index_path))
        
        # 保存 ID 映射
        with open(self.kb_id_map_path, 'wb') as f:
            pickle.dump(id_map, f)
        
        print(f"\n{'='*60}")
        print(f"🎉 知识库构建完成！")
        print(f"{'='*60}")
        print(f"📊 统计信息:")
        print(f"   ✓ 总片段数: {total_chunks}")
        print(f"   ✓ 索引大小: {index.ntotal} 条")
        print(f"{'='*60}\n")
    
    def _build_from_cleaned_json(self, conn, cursor, index, id_map) -> int:
        """从清洗后的 JSON 数据构建知识库"""
        import json
        
        json_file = project_root / "data" / "cleaned_knowledge.json"
        
        if not json_file.exists():
            print(f"❌ 清洗后的数据文件不存在: {json_file}")
            print(f"   请先运行: python tools/kb_cleaner.py")
            return 0
        
        print(f"📖 从清洗后的数据构建知识库: {json_file}")
        
        # 读取 JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            metadata_list = json.load(f)
        
        print(f"✅ 加载 {len(metadata_list)} 条元数据")
        
        # 向量化并存储
        print(f"\n💾 正在向量化并存储...")
        print(f"进度: ", end="", flush=True)
        
        for i, metadata in enumerate(metadata_list):
            title = metadata.get('title', '')
            content = metadata.get('content', '')
            source = metadata.get('source', 'unknown')
            
            # 合并标题和内容（用于向量化）
            full_text = f"{title}：{content}"
            
            # 生成向量
            embedding = self.embedding_client.get_embedding(full_text)
            # 归一化
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            
            # 存储元数据到 SQLite
            cursor.execute("""
                INSERT INTO knowledge (source, content, title)
                VALUES (?, ?, ?)
            """, (source, content, title))
            
            kb_id = cursor.lastrowid
            
            # 添加向量到 FAISS
            index.add(embedding.reshape(1, -1))
            id_map.append(kb_id)
            
            # 显示进度
            progress = ((i + 1) / len(metadata_list)) * 100
            bar_length = 30
            filled = int(bar_length * (i + 1) / len(metadata_list))
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\r进度: [{bar}] {progress:.1f}% ({i+1}/{len(metadata_list)})", end="", flush=True)
        
        print()
        print(f"✅ 存储完成！")
        
        return len(metadata_list)
    
    def _build_from_raw_files(self, conn, cursor, index, id_map) -> int:
        """从原始 txt 文件构建知识库（旧模式）"""
        # 4. 扫描文档
        docs_dir = project_root / "knowledge_docs"
        if not docs_dir.exists():
            print(f"❌ 文档文件夹不存在: {docs_dir}")
            print(f"   请创建 knowledge_docs/ 文件夹并放入 .txt 或 .md 文件")
            return 0
        
        files = glob.glob(str(docs_dir / "*.txt")) + glob.glob(str(docs_dir / "*.md"))
        
        if not files:
            print("❌ 未发现任何文档")
            return 0
        
        print(f"\n📚 发现 {len(files)} 个文档，开始处理...\n")
        
        # 5. 处理每个文件
        total_chunks = 0
        for file_idx, file_path in enumerate(files, 1):
            filename = os.path.basename(file_path)
            print(f"\n{'='*60}")
            print(f"📄 [{file_idx}/{len(files)}] 正在处理: {filename}")
            print(f"{'='*60}")
            
            try:
                # 读取文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if not content.strip():
                    print(f"⚠️  文件为空，跳过\n")
                    continue
                
                print(f"✅ 文件大小: {len(content)} 字符")
                
                # 文本切片
                print(f"✂️  正在切分文本...")
                chunks = self.split_text(content)
                print(f"✅ 切分完成: {len(chunks)} 个片段")
                
                # 向量化并存储
                print(f"\n💾 正在向量化并存储...")
                print(f"进度: ", end="", flush=True)
                
                for i, chunk in enumerate(chunks):
                    # 生成向量
                    embedding = self.embedding_client.get_embedding(chunk)
                    # 归一化
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                    
                    # 存储元数据到 SQLite
                    cursor.execute("""
                        INSERT INTO knowledge (source, content, title)
                        VALUES (?, ?, ?)
                    """, (filename, chunk, filename.rsplit('.', 1)[0]))
                    
                    kb_id = cursor.lastrowid
                    
                    # 添加向量到 FAISS
                    index.add(embedding.reshape(1, -1))
                    id_map.append(kb_id)
                    
                    # 显示进度
                    progress = ((i + 1) / len(chunks)) * 100
                    bar_length = 30
                    filled = int(bar_length * (i + 1) / len(chunks))
                    bar = '█' * filled + '░' * (bar_length - filled)
                    print(f"\r进度: [{bar}] {progress:.1f}% ({i+1}/{len(chunks)})", end="", flush=True)
                
                print()
                total_chunks += len(chunks)
                print(f"✅ 存储完成！")
                
            except Exception as e:
                print(f"\n❌ 处理失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return total_chunks


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🧠 知识库构建工具 v2.0 (FAISS + SQLite)")
    print("="*60 + "\n")
    
    try:
        builder = FAISSKBBuilder()
        
        print("📋 请选择数据源：")
        print("   [1] 使用清洗后的 JSON 数据（推荐，更清晰）")
        print("   [2] 使用原始 txt 文件（旧模式）")
        source_choice = input("\n请选择 (1/2): ").strip()
        
        use_cleaned = (source_choice == '1')
        
        print("\n⚠️  是否清空旧知识库？")
        print("   [Y] 是（全量更新，删除旧数据）")
        print("   [N] 否（增量更新，保留旧数据）")
        clear_choice = input("\n请选择 (Y/N): ").strip().upper()
        
        clear_old = (clear_choice == 'Y')
        
        print()
        builder.run(clear_old=clear_old, use_cleaned=use_cleaned)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 构建失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
