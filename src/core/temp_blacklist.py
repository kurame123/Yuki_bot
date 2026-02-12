"""
临时黑名单模块
用于 Injection Guard 将疑似注入攻击的用户拉入临时小黑屋
支持手动管理、统计查询、自动清理
"""
import time
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from src.core.logger import logger


class TempBlacklist:
    """临时黑名单管理器（基于 SQLite 持久化）"""
    
    def __init__(self, db_path: str = "./data/guard.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temp_blacklist (
                user_id TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL,
                reason TEXT,
                blocked_at INTEGER NOT NULL,
                blocked_by TEXT DEFAULT 'auto_guard',
                hit_count INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()
    
    def ban(self, user_id: str, minutes: int, reason: Optional[str] = None, by: str = "auto_guard") -> Dict:
        """
        将用户拉入小黑屋
        
        Args:
            user_id: 用户 ID
            minutes: 封禁时长（分钟）
            reason: 封禁原因（可选）
            by: 封禁操作者（auto_guard / admin_qq号）
            
        Returns:
            封禁信息字典
        """
        expires_at = int(time.time()) + minutes * 60
        blocked_at = int(time.time())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 检查是否已存在
        cursor.execute("SELECT hit_count FROM temp_blacklist WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            # 已存在，更新并增加命中次数
            hit_count = row[0] + 1
            cursor.execute("""
                UPDATE temp_blacklist 
                SET expires_at = ?, reason = ?, blocked_at = ?, blocked_by = ?, hit_count = ?
                WHERE user_id = ?
            """, (expires_at, reason, blocked_at, by, hit_count, user_id))
        else:
            # 新增
            hit_count = 1
            cursor.execute("""
                INSERT INTO temp_blacklist (user_id, expires_at, reason, blocked_at, blocked_by, hit_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, expires_at, reason, blocked_at, by, hit_count))
        
        conn.commit()
        conn.close()
        
        logger.warning(f"🚫 用户 {user_id} 被拉入小黑屋 {minutes} 分钟，原因：{reason or '未指定'}，操作者：{by}")
        
        return {
            "user_id": user_id,
            "expires_at": expires_at,
            "remaining_minutes": minutes,
            "reason": reason,
            "blocked_by": by,
            "hit_count": hit_count
        }
    
    def unban(self, user_id: str) -> bool:
        """
        解除用户封禁
        
        Args:
            user_id: 用户 ID
            
        Returns:
            True 表示成功解封，False 表示用户本来就不在黑名单
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM temp_blacklist WHERE user_id = ?", (user_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logger.info(f"✅ 用户 {user_id} 已解除封禁")
            return True
        else:
            return False
    
    def is_blocked(self, user_id: str) -> bool:
        """
        检查用户是否在黑名单中
        
        Args:
            user_id: 用户 ID
            
        Returns:
            True 表示在黑名单中，False 表示不在
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT expires_at FROM temp_blacklist WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False
        
        expires_at = row[0]
        now = int(time.time())
        
        # 如果已过期，自动清理
        if now >= expires_at:
            self.unban(user_id)
            return False
        
        return True
    
    def get_info(self, user_id: str) -> Optional[Dict]:
        """
        获取用户的封禁信息
        
        Args:
            user_id: 用户 ID
            
        Returns:
            封禁信息字典或 None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT expires_at, reason, blocked_at, blocked_by, hit_count 
            FROM temp_blacklist WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        expires_at, reason, blocked_at, blocked_by, hit_count = row
        now = int(time.time())
        
        # 如果已过期，自动清理
        if now >= expires_at:
            self.unban(user_id)
            return None
        
        remaining_seconds = expires_at - now
        remaining_minutes = remaining_seconds // 60
        
        return {
            "user_id": user_id,
            "expires_at": expires_at,
            "remaining_minutes": remaining_minutes,
            "remaining_seconds": remaining_seconds,
            "reason": reason,
            "blocked_at": blocked_at,
            "blocked_by": blocked_by,
            "hit_count": hit_count
        }
    
    def extend(self, user_id: str, minutes: int) -> Optional[Dict]:
        """
        延长用户封禁时间
        
        Args:
            user_id: 用户 ID
            minutes: 延长的分钟数
            
        Returns:
            更新后的封禁信息或 None
        """
        info = self.get_info(user_id)
        if not info:
            return None
        
        new_expires_at = info["expires_at"] + minutes * 60
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE temp_blacklist SET expires_at = ? WHERE user_id = ?
        """, (new_expires_at, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"⏰ 用户 {user_id} 封禁时间延长 {minutes} 分钟")
        
        return self.get_info(user_id)
    
    def list_active(self, page: int = 1, page_size: int = 10) -> Dict:
        """
        列出当前活跃的封禁记录（分页）
        
        Args:
            page: 页码（从 1 开始）
            page_size: 每页条数
            
        Returns:
            包含记录列表和分页信息的字典
        """
        now = int(time.time())
        offset = (page - 1) * page_size
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取总数
        cursor.execute("SELECT COUNT(*) FROM temp_blacklist WHERE expires_at > ?", (now,))
        total = cursor.fetchone()[0]
        
        # 获取分页数据
        cursor.execute("""
            SELECT user_id, expires_at, reason, blocked_at, blocked_by, hit_count
            FROM temp_blacklist 
            WHERE expires_at > ?
            ORDER BY expires_at DESC
            LIMIT ? OFFSET ?
        """, (now, page_size, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            user_id, expires_at, reason, blocked_at, blocked_by, hit_count = row
            remaining_seconds = expires_at - now
            remaining_minutes = remaining_seconds // 60
            
            records.append({
                "user_id": user_id,
                "expires_at": expires_at,
                "remaining_minutes": remaining_minutes,
                "reason": reason,
                "blocked_at": blocked_at,
                "blocked_by": blocked_by,
                "hit_count": hit_count
            })
        
        total_pages = (total + page_size - 1) // page_size
        
        return {
            "records": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    
    def stats(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        now = int(time.time())
        today_start = now - (now % 86400)  # 今天 0 点
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 当前活跃封禁数
        cursor.execute("SELECT COUNT(*) FROM temp_blacklist WHERE expires_at > ?", (now,))
        active_count = cursor.fetchone()[0]
        
        # 今日新增封禁数
        cursor.execute("SELECT COUNT(*) FROM temp_blacklist WHERE blocked_at >= ?", (today_start,))
        today_count = cursor.fetchone()[0]
        
        # 最常见原因
        cursor.execute("""
            SELECT reason, COUNT(*) as cnt 
            FROM temp_blacklist 
            GROUP BY reason 
            ORDER BY cnt DESC 
            LIMIT 5
        """)
        top_reasons = [{"reason": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        # 命中次数 Top 5
        cursor.execute("""
            SELECT user_id, hit_count 
            FROM temp_blacklist 
            WHERE expires_at > ?
            ORDER BY hit_count DESC 
            LIMIT 5
        """, (now,))
        top_offenders = [{"user_id": row[0], "hit_count": row[1]} for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "active_count": active_count,
            "today_count": today_count,
            "top_reasons": top_reasons,
            "top_offenders": top_offenders
        }
    
    def cleanup_expired(self) -> int:
        """
        清理所有过期记录
        
        Returns:
            清理的记录数量
        """
        now = int(time.time())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM temp_blacklist WHERE expires_at < ?", (now,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logger.info(f"🧹 清理了 {deleted} 条过期黑名单记录")
        
        return deleted


# 全局单例
_temp_blacklist_instance = None

def get_temp_blacklist() -> TempBlacklist:
    """获取临时黑名单实例（单例）"""
    global _temp_blacklist_instance
    if _temp_blacklist_instance is None:
        _temp_blacklist_instance = TempBlacklist()
    return _temp_blacklist_instance
