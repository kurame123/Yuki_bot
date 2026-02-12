"""
统计服务模块 - 负责所有统计相关的读写
"""
import sqlite3
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any, List
from src.core.logger import logger


class StatsService:
    """
    统计服务（单例模式）
    
    负责：
    - 用户统计（总用户数、新用户）
    - 消息统计（收发消息数）
    - LLM 使用统计（token 用量、调用次数、成本）
    - 日统计（用于图表展示）
    """
    
    _instance: Optional['StatsService'] = None
    _lock = threading.Lock()
    
    # 成本计算常量（RMB / 百万 token）
    COST_RATES = {
        "deepseek-r1": 16.0 / 1_000_000,      # DeepSeek-R1: 16 RMB / 1M tokens
        "deepseek-v3": 3.0 / 1_000_000,       # DeepSeek-V3: 3 RMB / 1M tokens
    }
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.db_path = Path("data/stats.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._cache: Dict[str, Any] = {}
        self._users_set: set = set()  # 用于快速判断用户是否存在
        
        # 初始化数据库
        self._init_database()
        self._load_cache()
        
        logger.info("✅ Stats Service initialized")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self) -> None:
        """初始化数据库表结构"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 全局统计表（仅一行）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS global_stats (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_users INTEGER DEFAULT 0,
                    total_msg_received INTEGER DEFAULT 0,
                    total_msg_sent INTEGER DEFAULT 0,
                    r1_input_tokens INTEGER DEFAULT 0,
                    r1_output_tokens INTEGER DEFAULT 0,
                    r1_calls INTEGER DEFAULT 0,
                    v3_input_tokens INTEGER DEFAULT 0,
                    v3_output_tokens INTEGER DEFAULT 0,
                    v3_calls INTEGER DEFAULT 0,
                    updated_at TEXT
                )
            """)
            
            # 插入初始行（如果不存在）
            cursor.execute("""
                INSERT OR IGNORE INTO global_stats (id) VALUES (1)
            """)
            
            # 用户统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id TEXT PRIMARY KEY,
                    first_seen TEXT,
                    last_seen TEXT,
                    msg_received INTEGER DEFAULT 0,
                    msg_sent INTEGER DEFAULT 0
                )
            """)
            
            # 日统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    msg_received INTEGER DEFAULT 0,
                    msg_sent INTEGER DEFAULT 0,
                    r1_input_tokens INTEGER DEFAULT 0,
                    r1_output_tokens INTEGER DEFAULT 0,
                    r1_calls INTEGER DEFAULT 0,
                    v3_input_tokens INTEGER DEFAULT 0,
                    v3_output_tokens INTEGER DEFAULT 0,
                    v3_calls INTEGER DEFAULT 0
                )
            """)
            
            conn.commit()
            logger.debug("📊 Stats database initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to init stats database: {e}")
            raise
        finally:
            conn.close()
    
    def _load_cache(self) -> None:
        """从数据库加载缓存"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 加载全局统计
            cursor.execute("SELECT * FROM global_stats WHERE id = 1")
            row = cursor.fetchone()
            if row:
                self._cache = {
                    'total_users': row['total_users'] or 0,
                    'total_msg_received': row['total_msg_received'] or 0,
                    'total_msg_sent': row['total_msg_sent'] or 0,
                    'r1_input_tokens': row['r1_input_tokens'] or 0,
                    'r1_output_tokens': row['r1_output_tokens'] or 0,
                    'r1_calls': row['r1_calls'] or 0,
                    'v3_input_tokens': row['v3_input_tokens'] or 0,
                    'v3_output_tokens': row['v3_output_tokens'] or 0,
                    'v3_calls': row['v3_calls'] or 0,
                }
            
            # 加载用户 ID 集合
            cursor.execute("SELECT user_id FROM user_stats")
            self._users_set = {row['user_id'] for row in cursor.fetchall()}
            
            logger.debug(f"📊 Cache loaded: {self._cache['total_users']} users, "
                        f"{self._cache['total_msg_received']} msgs received")
            
        except Exception as e:
            logger.error(f"❌ Failed to load stats cache: {e}")
            # 使用默认值
            self._cache = {
                'total_users': 0, 'total_msg_received': 0, 'total_msg_sent': 0,
                'r1_input_tokens': 0, 'r1_output_tokens': 0, 'r1_calls': 0,
                'v3_input_tokens': 0, 'v3_output_tokens': 0, 'v3_calls': 0,
            }
        finally:
            conn.close()

    def _save_global_stats(self) -> None:
        """保存全局统计到数据库"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE global_stats SET
                    total_users = ?,
                    total_msg_received = ?,
                    total_msg_sent = ?,
                    r1_input_tokens = ?,
                    r1_output_tokens = ?,
                    r1_calls = ?,
                    v3_input_tokens = ?,
                    v3_output_tokens = ?,
                    v3_calls = ?,
                    updated_at = ?
                WHERE id = 1
            """, (
                self._cache['total_users'],
                self._cache['total_msg_received'],
                self._cache['total_msg_sent'],
                self._cache['r1_input_tokens'],
                self._cache['r1_output_tokens'],
                self._cache['r1_calls'],
                self._cache['v3_input_tokens'],
                self._cache['v3_output_tokens'],
                self._cache['v3_calls'],
                datetime.now().isoformat()
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to save global stats: {e}")
        finally:
            conn.close()
    
    def _get_today_str(self) -> str:
        """获取今天的日期字符串"""
        return date.today().isoformat()
    
    # ============ 公开接口方法 ============
    
    def record_incoming_message(self, user_id: str) -> None:
        """
        记录收到的消息
        
        Args:
            user_id: 用户 ID
        """
        now = datetime.now().isoformat()
        today = self._get_today_str()
        
        # 更新内存缓存
        self._cache['total_msg_received'] += 1
        
        # 检查是否是新用户
        is_new_user = user_id not in self._users_set
        if is_new_user:
            self._cache['total_users'] += 1
            self._users_set.add(user_id)
        
        # 写入数据库
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 更新或插入用户统计
            if is_new_user:
                cursor.execute("""
                    INSERT INTO user_stats (user_id, first_seen, last_seen, msg_received)
                    VALUES (?, ?, ?, 1)
                """, (user_id, now, now))
            else:
                cursor.execute("""
                    UPDATE user_stats SET
                        last_seen = ?,
                        msg_received = msg_received + 1
                    WHERE user_id = ?
                """, (now, user_id))
            
            # 更新日统计
            cursor.execute("""
                INSERT INTO daily_stats (date, msg_received)
                VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    msg_received = msg_received + 1
            """, (today,))
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to record incoming message: {e}")
        finally:
            conn.close()
        
        # 保存全局统计
        self._save_global_stats()
    
    def record_outgoing_message(self, user_id: str) -> None:
        """
        记录发送的消息
        
        Args:
            user_id: 用户 ID
        """
        today = self._get_today_str()
        
        # 更新内存缓存
        self._cache['total_msg_sent'] += 1
        
        # 写入数据库
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 更新用户统计
            cursor.execute("""
                UPDATE user_stats SET msg_sent = msg_sent + 1
                WHERE user_id = ?
            """, (user_id,))
            
            # 更新日统计
            cursor.execute("""
                INSERT INTO daily_stats (date, msg_sent)
                VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    msg_sent = msg_sent + 1
            """, (today,))
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to record outgoing message: {e}")
        finally:
            conn.close()
        
        # 保存全局统计
        self._save_global_stats()
    
    def record_llm_usage(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int
    ) -> None:
        """
        记录 LLM 使用量
        
        Args:
            model_name: 模型名称（如 "deepseek-ai/DeepSeek-R1"）
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
        """
        today = self._get_today_str()
        
        # 识别模型类型
        model_lower = model_name.lower()
        if "r1" in model_lower:
            model_type = "r1"
        elif "v3" in model_lower or "deepseek-v" in model_lower:
            model_type = "v3"
        else:
            logger.warning(f"Unknown model type: {model_name}, treating as v3")
            model_type = "v3"
        
        # 更新内存缓存
        self._cache[f'{model_type}_input_tokens'] += input_tokens
        self._cache[f'{model_type}_output_tokens'] += output_tokens
        self._cache[f'{model_type}_calls'] += 1
        
        # 写入数据库
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if model_type == "r1":
                cursor.execute("""
                    INSERT INTO daily_stats (date, r1_input_tokens, r1_output_tokens, r1_calls)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(date) DO UPDATE SET
                        r1_input_tokens = r1_input_tokens + ?,
                        r1_output_tokens = r1_output_tokens + ?,
                        r1_calls = r1_calls + 1
                """, (today, input_tokens, output_tokens, input_tokens, output_tokens))
            else:
                cursor.execute("""
                    INSERT INTO daily_stats (date, v3_input_tokens, v3_output_tokens, v3_calls)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(date) DO UPDATE SET
                        v3_input_tokens = v3_input_tokens + ?,
                        v3_output_tokens = v3_output_tokens + ?,
                        v3_calls = v3_calls + 1
                """, (today, input_tokens, output_tokens, input_tokens, output_tokens))
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to record LLM usage: {e}")
        finally:
            conn.close()
        
        # 保存全局统计
        self._save_global_stats()
        
        logger.debug(f"📊 LLM usage recorded: {model_type} +{input_tokens}/{output_tokens} tokens")

    def get_global_stats(self) -> Dict[str, Any]:
        """
        获取全局统计数据
        
        Returns:
            包含所有统计数据的字典
        """
        # 计算成本
        r1_tokens = self._cache['r1_input_tokens'] + self._cache['r1_output_tokens']
        v3_tokens = self._cache['v3_input_tokens'] + self._cache['v3_output_tokens']
        
        r1_cost = r1_tokens * self.COST_RATES['deepseek-r1']
        v3_cost = v3_tokens * self.COST_RATES['deepseek-v3']
        total_cost = r1_cost + v3_cost
        
        return {
            # 用户统计
            'total_users': self._cache['total_users'],
            
            # 消息统计
            'total_msg_received': self._cache['total_msg_received'],
            'total_msg_sent': self._cache['total_msg_sent'],
            
            # R1 模型统计
            'r1_input_tokens': self._cache['r1_input_tokens'],
            'r1_output_tokens': self._cache['r1_output_tokens'],
            'r1_calls': self._cache['r1_calls'],
            'r1_cost': round(r1_cost, 4),
            
            # V3 模型统计
            'v3_input_tokens': self._cache['v3_input_tokens'],
            'v3_output_tokens': self._cache['v3_output_tokens'],
            'v3_calls': self._cache['v3_calls'],
            'v3_cost': round(v3_cost, 4),
            
            # 总成本
            'total_cost': round(total_cost, 4),
            
            # 时间戳
            'updated_at': datetime.now().isoformat(),
        }
    
    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取最近 N 天的日统计数据
        
        Args:
            days: 天数（默认 7 天）
            
        Returns:
            日统计数据列表
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM daily_stats
                ORDER BY date DESC
                LIMIT ?
            """, (days,))
            
            rows = cursor.fetchall()
            result = []
            
            for row in rows:
                r1_tokens = (row['r1_input_tokens'] or 0) + (row['r1_output_tokens'] or 0)
                v3_tokens = (row['v3_input_tokens'] or 0) + (row['v3_output_tokens'] or 0)
                r1_cost = r1_tokens * self.COST_RATES['deepseek-r1']
                v3_cost = v3_tokens * self.COST_RATES['deepseek-v3']
                
                result.append({
                    'date': row['date'],
                    'msg_received': row['msg_received'] or 0,
                    'msg_sent': row['msg_sent'] or 0,
                    'r1_tokens': r1_tokens,
                    'v3_tokens': v3_tokens,
                    'r1_calls': row['r1_calls'] or 0,
                    'v3_calls': row['v3_calls'] or 0,
                    'cost': round(r1_cost + v3_cost, 4),
                })
            
            # 按日期正序返回（方便图表展示）
            return list(reversed(result))
            
        except Exception as e:
            logger.error(f"❌ Failed to get daily stats: {e}")
            return []
        finally:
            conn.close()
    
    def get_today_stats(self) -> Dict[str, Any]:
        """获取今日统计"""
        today = self._get_today_str()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_stats WHERE date = ?", (today,))
            row = cursor.fetchone()
            
            if row:
                r1_tokens = (row['r1_input_tokens'] or 0) + (row['r1_output_tokens'] or 0)
                v3_tokens = (row['v3_input_tokens'] or 0) + (row['v3_output_tokens'] or 0)
                return {
                    'msg_received': row['msg_received'] or 0,
                    'msg_sent': row['msg_sent'] or 0,
                    'r1_tokens': r1_tokens,
                    'v3_tokens': v3_tokens,
                    'r1_calls': row['r1_calls'] or 0,
                    'v3_calls': row['v3_calls'] or 0,
                }
            return {
                'msg_received': 0, 'msg_sent': 0,
                'r1_tokens': 0, 'v3_tokens': 0,
                'r1_calls': 0, 'v3_calls': 0,
            }
        except Exception as e:
            logger.error(f"❌ Failed to get today stats: {e}")
            return {}
        finally:
            conn.close()
    
    def get_recent_active_users(self, limit: int = 20) -> List[str]:
        """
        获取最近活跃的用户列表（按最后活跃时间排序）
        
        Args:
            limit: 返回的用户数量上限
            
        Returns:
            用户 ID 列表
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id FROM user_stats
                ORDER BY last_seen DESC
                LIMIT ?
            """, (limit,))
            
            return [row['user_id'] for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"❌ Failed to get recent active users: {e}")
            return []
        finally:
            conn.close()


# ============ 单例获取函数 ============

_stats_service: Optional[StatsService] = None


def get_stats_service() -> StatsService:
    """获取统计服务单例"""
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService()
    return _stats_service
