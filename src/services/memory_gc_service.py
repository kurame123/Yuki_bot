"""
记忆垃圾回收服务 - 自动清理和压缩长期记忆（适配双数据库架构）

策略：
- 记忆条数 > 200：直接删除最旧的 15%
- 记忆条数 > 150：压缩最旧的 20% 为摘要
- 每 12 小时自动执行一次
- 可通过 /debot 命令手动触发
"""
import math
import time
import sqlite3
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from src.core.logger import logger
from src.core.config_manager import ConfigManager


@dataclass
class GCResult:
    """GC 执行结果"""
    user_id: str
    before_count: int
    after_count: int
    deleted_count: int
    summarized_count: int
    summary_generated: int
    error: Optional[str] = None


class MemoryGCService:
    """记忆垃圾回收服务（双数据库架构）"""
    
    # GC 阈值配置
    DELETE_THRESHOLD = 200      # 超过此数量触发删除
    DELETE_RATIO = 0.15         # 删除比例
    SUMMARIZE_THRESHOLD = 150   # 超过此数量触发压缩
    SUMMARIZE_RATIO = 0.20      # 压缩比例
    
    # 摘要配置
    SUMMARY_MAX_CHARS = 500     # 摘要最大字符数
    BATCH_SIZE = 15             # 每批压缩的记忆条数
    
    def __init__(self):
        bot_config = ConfigManager.get_bot_config()
        self.db_base = Path(bot_config.storage.vector_db_path)
        self.private_dir = self.db_base / "private"
    
    def get_user_memory_count(self, user_id: str) -> int:
        """获取用户记忆条数（私聊 + 群聊）"""
        try:
            db_path = self.private_dir / user_id / "private.db"
            if not db_path.exists():
                return 0
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 统计私聊记忆
            cursor.execute("SELECT COUNT(*) FROM private_memories")
            private_count = cursor.fetchone()[0]
            
            # 统计群聊记忆
            try:
                cursor.execute("SELECT COUNT(*) FROM group_memories")
                group_count = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                group_count = 0
            
            conn.close()
            
            return private_count + group_count
            
        except Exception as e:
            logger.error(f"获取用户 {user_id} 记忆数失败: {e}")
            return 0
    
    def get_oldest_memories(
        self, 
        user_id: str, 
        limit: int
    ) -> Tuple[List[int], List[str], str]:
        """
        获取用户最旧的 N 条记忆
        
        Returns:
            (ids, documents, table_name)
        """
        try:
            db_path = self.private_dir / user_id / "private.db"
            if not db_path.exists():
                return [], [], ""
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 从私聊记忆中获取最旧的
            cursor.execute("""
                SELECT id, content, timestamp FROM private_memories
                ORDER BY timestamp ASC
                LIMIT ?
            """, (limit,))
            
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return [], [], ""
            
            ids = [r[0] for r in results]
            docs = [r[1] for r in results]
            
            return ids, docs, "private_memories"
            
        except Exception as e:
            logger.error(f"获取用户 {user_id} 最旧记忆失败: {e}")
            return [], [], ""
    
    async def summarize_memories(
        self, 
        user_id: str, 
        documents: List[str]
    ) -> List[str]:
        """
        使用场景模型压缩记忆为摘要
        
        Args:
            user_id: 用户 ID
            documents: 要压缩的记忆文本列表
            
        Returns:
            摘要文本列表
        """
        if not documents:
            return []
        
        try:
            config = ConfigManager.get_ai_config()
            from src.services.http_client import AsyncHTTPClient
            from src.models.api_types import ChatMessage
            
            # 将记忆分批处理
            summaries = []
            for i in range(0, len(documents), self.BATCH_SIZE):
                batch = documents[i:i + self.BATCH_SIZE]
                batch_text = "\n---\n".join(batch)
                
                # 构建压缩 prompt
                prompt = f"""请将以下对话记忆压缩成一段简洁的摘要，不超过{self.SUMMARY_MAX_CHARS}字。
保留关键事件、情感变化和重要信息，不要逐条复述。

对话记忆：
{batch_text}

摘要："""
                
                messages = [ChatMessage(role="user", content=prompt)]
                
                # 获取供应商配置
                provider_name = config.common.default_provider
                providers = config.providers
                if provider_name in providers:
                    provider = providers[provider_name]
                    api_base = provider.api_base
                    api_key = provider.api_key
                elif hasattr(config.common, 'api_base') and config.common.api_base:
                    api_base = config.common.api_base
                    api_key = config.common.api_key
                else:
                    raise ValueError(f"未找到供应商配置: {provider_name}")
                
                async with AsyncHTTPClient(timeout=60) as client:
                    response = await client.chat_completion(
                        api_base=api_base,
                        api_key=api_key,
                        model=config.organizer.model_name,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=600,
                        timeout=60
                    )
                    
                    summary = AsyncHTTPClient.parse_completion_response(response)
                    if summary:
                        summaries.append(summary.strip())
            
            logger.info(f"📝 用户 {user_id}: {len(documents)} 条记忆压缩为 {len(summaries)} 条摘要")
            return summaries
            
        except Exception as e:
            logger.error(f"压缩记忆失败: {e}")
            return []
    
    def insert_summary_and_delete(
        self,
        user_id: str,
        old_ids: List[int],
        summaries: List[str],
        table_name: str
    ) -> bool:
        """
        插入摘要并删除原始记忆（双数据库架构）
        
        注意：需要同时更新 SQLite 和 FAISS 索引
        """
        try:
            db_path = self.private_dir / user_id / "private.db"
            if not db_path.exists():
                return False
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # 插入摘要到数据库
            for summary in summaries:
                cursor.execute(f"""
                    INSERT INTO {table_name} (role, content, timestamp, query, reply)
                    VALUES (?, ?, ?, ?, ?)
                """, ("summary", summary, int(time.time()), None, None))
            
            # 删除原始记忆
            if old_ids:
                placeholders = ','.join('?' * len(old_ids))
                cursor.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", old_ids)
            
            conn.commit()
            conn.close()
            
            # TODO: 重建 FAISS 索引（可选，或者在下次启动时自动重建）
            logger.info(f"🗑️ 用户 {user_id}: 删除 {len(old_ids)} 条旧记忆，插入 {len(summaries)} 条摘要")
            logger.warning(f"⚠️ FAISS 索引未更新，建议重启 Bot 或手动重建索引")
            
            return True
            
        except Exception as e:
            logger.error(f"插入摘要/删除记忆失败: {e}")
            return False
    
    def delete_oldest(self, user_id: str, ratio: float) -> int:
        """
        删除用户最旧的一定比例记忆
        
        Args:
            user_id: 用户 ID
            ratio: 删除比例 (0-1)
            
        Returns:
            删除的条数
        """
        try:
            count = self.get_user_memory_count(user_id)
            if count == 0:
                return 0
            
            limit = math.ceil(count * ratio)
            old_ids, _, table_name = self.get_oldest_memories(user_id, limit)
            
            if old_ids and table_name:
                db_path = self.private_dir / user_id / "private.db"
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                placeholders = ','.join('?' * len(old_ids))
                cursor.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", old_ids)
                
                conn.commit()
                conn.close()
                
                logger.info(f"🗑️ 用户 {user_id}: 直接删除 {len(old_ids)} 条最旧记忆")
                logger.warning(f"⚠️ FAISS 索引未更新，建议重启 Bot 或手动重建索引")
            
            return len(old_ids)
            
        except Exception as e:
            logger.error(f"删除最旧记忆失败: {e}")
            return 0
    
    async def gc_user(self, user_id: str) -> GCResult:
        """
        对单个用户执行 GC
        
        策略：
        1. N > 200: 先删除 15% 最旧的
        2. N > 150: 压缩 20% 最旧的为摘要
        """
        result = GCResult(
            user_id=user_id,
            before_count=0,
            after_count=0,
            deleted_count=0,
            summarized_count=0,
            summary_generated=0
        )
        
        try:
            # 获取初始数量
            result.before_count = self.get_user_memory_count(user_id)
            current_count = result.before_count
            
            logger.info(f"🔄 开始 GC 用户 {user_id}: {current_count} 条记忆")
            
            # 阶段 1: 超过 200 条，直接删除 15%
            if current_count > self.DELETE_THRESHOLD:
                deleted = self.delete_oldest(user_id, self.DELETE_RATIO)
                result.deleted_count = deleted
                current_count = self.get_user_memory_count(user_id)
            
            # 阶段 2: 超过 150 条，压缩 20%
            if current_count > self.SUMMARIZE_THRESHOLD:
                limit = math.ceil(current_count * self.SUMMARIZE_RATIO)
                old_ids, docs, table_name = self.get_oldest_memories(user_id, limit)
                
                if docs:
                    # 压缩记忆
                    summaries = await self.summarize_memories(user_id, docs)
                    
                    if summaries:
                        # 插入摘要并删除原始
                        self.insert_summary_and_delete(user_id, old_ids, summaries, table_name)
                        result.summarized_count = len(old_ids)
                        result.summary_generated = len(summaries)
            
            # 获取最终数量
            result.after_count = self.get_user_memory_count(user_id)
            
            logger.info(
                f"✅ GC 完成 用户 {user_id}: "
                f"{result.before_count} → {result.after_count} 条 "
                f"(删除 {result.deleted_count}, 压缩 {result.summarized_count})"
            )
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ GC 用户 {user_id} 失败: {e}")
        
        return result
    
    def get_all_user_ids(self) -> List[str]:
        """获取所有有记忆的用户 ID"""
        try:
            if not self.private_dir.exists():
                return []
            
            user_ids = []
            for user_dir in self.private_dir.iterdir():
                if user_dir.is_dir():
                    user_ids.append(user_dir.name)
            
            return user_ids
            
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []
    
    async def gc_all_users(self) -> List[GCResult]:
        """对所有用户执行 GC"""
        user_ids = self.get_all_user_ids()
        logger.info(f"🔄 开始全局 GC，共 {len(user_ids)} 个用户")
        
        results = []
        for user_id in user_ids:
            result = await self.gc_user(user_id)
            results.append(result)
            
            # 每个用户之间稍微延迟，避免 API 限流
            await asyncio.sleep(0.5)
        
        # 统计
        total_deleted = sum(r.deleted_count for r in results)
        total_summarized = sum(r.summarized_count for r in results)
        total_summaries = sum(r.summary_generated for r in results)
        
        logger.info(
            f"✅ 全局 GC 完成: "
            f"处理 {len(results)} 用户, "
            f"删除 {total_deleted} 条, "
            f"压缩 {total_summarized} 条 → {total_summaries} 条摘要"
        )
        
        return results


# 全局单例
_gc_service: Optional[MemoryGCService] = None


def get_memory_gc_service() -> MemoryGCService:
    """获取记忆 GC 服务单例"""
    global _gc_service
    if _gc_service is None:
        _gc_service = MemoryGCService()
    return _gc_service
