"""
好感度系统服务 - AffectionService
负责管理用户与 Yuki 的好感度数据
"""
import os
import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from src.core.logger import logger


class AffectionService:
    """
    好感度服务（单例）
    
    职责：
    1. 管理 data/affection.db 数据库
    2. 实现好感度评分算法
    3. 提供好感度读写接口
    4. 根据好感度返回对应温度
    """
    
    _instance: Optional['AffectionService'] = None
    
    # === 等级定义 ===
    LEVEL_NAMES = {
        -2: "讨厌",
        -1: "差劲",
        0: "不起眼",
        1: "陌生",
        2: "一般", 
        3: "稍熟",
        4: "熟悉",
        5: "热情",
        6: "亲密",
        7: "喜欢",
        8: "喜欢+",
        9: "爱慕",
        10: "深爱",
        11: "挚爱",
        12: "命运",
        13: "永恒"
    }
    
    # 等级分数区间: (level, min_score, max_score)
    LEVEL_RANGES = [
        (-2, 0.0, 1.0),    # 讨厌
        (-1, 1.1, 2.0),    # 差劲
        (0, 2.1, 3.0),     # 不起眼
        (1, 3.1, 4.0),     # 陌生
        (2, 4.1, 5.0),     # 一般
        (3, 5.1, 6.0),     # 稍熟
        (4, 6.1, 7.0),     # 熟悉
        (5, 7.1, 8.0),     # 热情
        (6, 8.1, 9.0),     # 亲密
        (7, 9.1, 10.0),    # 喜欢
        (8, 10.1, 11.0),   # 喜欢+
        (9, 11.1, 11.5),   # 爱慕
        (10, 11.6, 12.0),  # 深爱
        (11, 12.1, 12.5),  # 挚爱
        (12, 12.6, 12.9),  # 命运
        (13, 13.0, 13.0)   # 永恒
    ]
    
    # 环境变量名映射
    TEMP_ENV_KEYS = {
        -2: "YUKI_AFF_TEMP_HATE",
        -1: "YUKI_AFF_TEMP_BAD",
        0: "YUKI_AFF_TEMP_UNNOTICED",
        1: "YUKI_AFF_TEMP_STRANGER",
        2: "YUKI_AFF_TEMP_NORMAL",
        3: "YUKI_AFF_TEMP_LITTLE",
        4: "YUKI_AFF_TEMP_FAMILIAR",
        5: "YUKI_AFF_TEMP_WARM",
        6: "YUKI_AFF_TEMP_INTIMATE",
        7: "YUKI_AFF_TEMP_LIKE",
        8: "YUKI_AFF_TEMP_LIKE_PLUS",
        9: "YUKI_AFF_TEMP_ADORE",
        10: "YUKI_AFF_TEMP_DEEP_LOVE",
        11: "YUKI_AFF_TEMP_TRUE_LOVE",
        12: "YUKI_AFF_TEMP_DESTINY",
        13: "YUKI_AFF_TEMP_ETERNAL"
    }

    # === 好感度算法词表 ===
    POSITIVE_LIGHT_WORDS = [
        "谢谢", "辛苦了", "真好", "可爱", "抱抱", "想你", "喜欢你",
        "厉害", "棒", "好棒", "开心", "高兴", "感谢", "爱你", "么么",
        "亲亲", "摸摸", "贴贴", "蹭蹭", "好喜欢", "超棒"
    ]
    
    POSITIVE_STRONG_WORDS = [
        "超喜欢你", "最爱你", "离不开你", "我爱你", "永远喜欢",
        "太爱了", "超级爱", "最喜欢你", "爱死你了"
    ]
    
    NEGATIVE_LIGHT_WORDS = [
        "无聊", "烦", "不高兴", "不开心", "累了", "算了", "懒得"
    ]
    
    NEGATIVE_STRONG_WORDS = [
        "讨厌你", "闭嘴", "滚", "垃圾", "傻逼", "不想理你",
        "烦死了", "去死", "恶心", "讨厌"
    ]
    
    EMOTICON_PATTERNS = [
        "~", "w", "ww", "qwq", "QwQ", "T_T", "TvT", "owo", "OwO",
        "哈哈", "嘿嘿", "嘻嘻", "呜呜", "(*´ω｀*)", "(´・ω・`)",
        "≧▽≦", "^_^", ">_<", "QAQ", "TAT"
    ]
    
    COLD_SHORT_REPLIES = ["嗯", "哦", "行", "好", "？", "?", "。", "...", "……"]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.db_path = Path("data/affection.db")
        self.level_temps: Dict[int, float] = {}
        
        # 从环境变量加载温度配置
        self._load_temp_config()
        
        logger.info("✅ AffectionService initialized")
    
    def _load_temp_config(self) -> None:
        """从环境变量加载各等级温度配置"""
        for level, env_key in self.TEMP_ENV_KEYS.items():
            value = os.getenv(env_key)
            if value:
                try:
                    self.level_temps[level] = float(value)
                except ValueError:
                    logger.warning(f"⚠️ 无法解析温度配置 {env_key}={value}")
        
        if self.level_temps:
            logger.info(f"   已加载 {len(self.level_temps)} 个等级温度配置")

    def init_db(self) -> None:
        """初始化数据库（同步方法，启动时调用）"""
        # 确保 data 目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_affection (
                user_id TEXT PRIMARY KEY,
                affection_score REAL DEFAULT 0.0,
                last_level INTEGER DEFAULT -2,
                total_interactions INTEGER DEFAULT 0,
                last_interact_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"✅ 好感度数据库初始化完成: {self.db_path}")
    
    # === 基础数据库操作 ===
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path), check_same_thread=False)
    
    def get_or_create_user(self, user_id: str) -> Tuple[float, int]:
        """
        获取或创建用户好感度记录
        
        Returns:
            (affection_score, last_level)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT affection_score, last_level FROM user_affection WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if row is None:
            # 新用户，插入初始记录（从"讨厌"开始）
            cursor.execute(
                """INSERT INTO user_affection 
                   (user_id, affection_score, last_level, total_interactions, last_interact_at)
                   VALUES (?, 0.0, -2, 0, ?)""",
                (user_id, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            return (0.0, -2)
        
        conn.close()
        return (row[0], row[1])
    
    def update_user(self, user_id: str, new_score: float, new_level: int) -> None:
        """更新用户好感度"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """UPDATE user_affection 
               SET affection_score = ?, last_level = ?, 
                   total_interactions = total_interactions + 1,
                   last_interact_at = ?
               WHERE user_id = ?""",
            (new_score, new_level, datetime.now().isoformat(), user_id)
        )
        
        conn.commit()
        conn.close()

    # === 等级/温度映射工具方法 ===
    
    def score_to_level(self, score: float) -> int:
        """根据分数计算等级"""
        for level, min_s, max_s in self.LEVEL_RANGES:
            if min_s <= score <= max_s:
                return level
        # 边界处理
        if score < 0.0:
            return -2
        if score > 13.0:
            return 13
        return -2
    
    def level_to_name(self, level: int) -> str:
        """获取等级名称"""
        return self.LEVEL_NAMES.get(level, "未知")
    
    def get_temperature_for_user(self, user_id: str, default_temp: float) -> float:
        """
        获取用户对应的模型温度
        
        Args:
            user_id: 用户 ID
            default_temp: 默认温度（来自 ai_model_config.toml）
            
        Returns:
            对应等级的温度，无记录时返回默认温度
        """
        score, _ = self.get_or_create_user(user_id)
        
        # 新用户（初始分数 0.0，讨厌等级）直接返回默认温度
        if score <= 0.0:
            return default_temp
        
        level = self.score_to_level(score)
        
        # 从配置的温度映射中获取，没有则返回默认
        return self.level_temps.get(level, default_temp)
    
    def get_affection_info_for_display(self, user_id: str) -> Dict[str, Any]:
        """
        获取用于显示的好感度信息
        
        Returns:
            {"score": float, "level": int, "level_name": str, "total_interactions": int}
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT affection_score, last_level, total_interactions 
               FROM user_affection WHERE user_id = ?""",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return {
                "score": 0.0,
                "level": -2,
                "level_name": "讨厌",
                "total_interactions": 0
            }
        
        score, level, interactions = row
        return {
            "score": round(score, 2),
            "level": level,
            "level_name": self.level_to_name(level),
            "total_interactions": interactions
        }

    # === 好感度更新算法（第 8-9 步）===
    
    async def update_affection(self, user_id: str, user_message: str, bot_reply: str) -> float:
        """
        更新用户好感度（每轮对话后调用）
        
        Args:
            user_id: 用户 ID
            user_message: 用户消息
            bot_reply: Bot 回复
            
        Returns:
            更新后的分数
        """
        # 使用 asyncio.to_thread 避免阻塞
        return await asyncio.to_thread(
            self._update_affection_sync, user_id, user_message, bot_reply
        )
    
    def _update_affection_sync(self, user_id: str, user_message: str, bot_reply: str) -> float:
        """同步版本的好感度更新"""
        # 1. 获取当前分数
        old_score, _ = self.get_or_create_user(user_id)
        
        # 2. 初始 delta（正常聊天微小上升）
        delta = 0.05
        
        u = user_message.strip()
        length = len(u)
        
        # 3. 认真程度加成
        if length > 40:
            delta += 0.05
        if length > 100:
            delta += 0.05
        
        # 4. 正向关键词加成
        light_hits = 0
        for word in self.POSITIVE_LIGHT_WORDS:
            if word in u:
                light_hits += 1
        delta += min(light_hits * 0.05, 0.15)  # 上限 +0.15
        
        for word in self.POSITIVE_STRONG_WORDS:
            if word in u:
                delta += 0.15
                break  # 只加一次
        
        # 5. 互动意愿加成（提问）
        if "?" in u or "？" in u:
            delta += 0.05
        
        # 6. 表情/颜文字加成
        for pattern in self.EMOTICON_PATTERNS:
            if pattern in u:
                delta += 0.05
                break
        
        # 7. 负面情绪减分
        for word in self.NEGATIVE_LIGHT_WORDS:
            if word in u:
                delta -= 0.1
                break
        
        for word in self.NEGATIVE_STRONG_WORDS:
            if word in u:
                delta -= 0.3
                break
        
        # 8. 冷淡短句惩罚
        if length <= 3 and u in self.COLD_SHORT_REPLIES:
            delta -= 0.05
        
        # 9. 根据当前分数调节成长速度
        if old_score <= 3.0:  # 讨厌到陌生阶段
            coef = 1.2  # 更容易脱离负面状态
        elif old_score <= 6.0:  # 陌生到稍熟
            coef = 1.0
        elif old_score <= 9.0:  # 稍熟到亲密
            coef = 0.7
        elif old_score <= 11.0:  # 亲密到喜欢+
            coef = 0.5
        elif old_score <= 12.5:  # 喜欢+到挚爱
            coef = 0.3
        else:  # 挚爱到永恒
            coef = 0.1  # 最高等级非常难达到
        
        delta *= coef
        
        # 10. 限制本轮变动幅度
        delta = max(-0.5, min(delta, 0.5))
        
        # 11. 计算新分数并截断（0.0 到 13.0）
        new_score = max(0.0, min(13.0, old_score + delta))
        new_level = self.score_to_level(new_score)
        
        # 12. 写回数据库
        self.update_user(user_id, new_score, new_level)
        
        # 日志记录（仅在分数变化较大时）
        if abs(delta) >= 0.1:
            logger.debug(
                f"💕 好感度更新: user={user_id}, "
                f"{old_score:.2f} -> {new_score:.2f} (Δ{delta:+.2f})"
            )
        
        return new_score

    # === Web 管理接口 ===

    async def get_overview(self) -> dict:
        """
        获取好感度总览统计（供 Web 使用）

        Returns:
            {
                "total_users": int,
                "avg_score": float,
                "level_counts": {1: int, 2: int, ..., 8: int}
            }
        """
        return await asyncio.to_thread(self._get_overview_sync)

    def _get_overview_sync(self) -> dict:
        """同步版本的总览统计"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 总用户数
        cursor.execute("SELECT COUNT(*) FROM user_affection")
        total_users = cursor.fetchone()[0]

        # 平均好感度
        cursor.execute("SELECT AVG(affection_score) FROM user_affection")
        avg_result = cursor.fetchone()[0]
        avg_score = round(avg_result, 2) if avg_result else 0.0

        # 各等级人数
        level_counts = {}
        for level in range(-2, 14):  # -2 到 13
            cursor.execute(
                "SELECT COUNT(*) FROM user_affection WHERE last_level = ?",
                (level,)
            )
            level_counts[level] = cursor.fetchone()[0]

        conn.close()

        return {
            "total_users": total_users,
            "avg_score": avg_score,
            "level_counts": level_counts
        }

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        level: int = None,
        keyword: str = None
    ) -> dict:
        """
        分页获取用户列表（供 Web 使用）

        Args:
            page: 页码（从 1 开始）
            page_size: 每页数量
            level: 筛选等级（可选）
            keyword: 搜索用户 ID（可选）

        Returns:
            {
                "items": [...],
                "total": int,
                "page": int,
                "page_size": int
            }
        """
        return await asyncio.to_thread(
            self._list_users_sync, page, page_size, level, keyword
        )

    def _list_users_sync(
        self,
        page: int,
        page_size: int,
        level: int,
        keyword: str
    ) -> dict:
        """同步版本的用户列表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 构建 WHERE 条件
        conditions = []
        params = []

        if level is not None:
            conditions.append("last_level = ?")
            params.append(level)

        if keyword:
            conditions.append("user_id LIKE ?")
            params.append(f"%{keyword}%")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 查询总数
        count_sql = f"SELECT COUNT(*) FROM user_affection {where_clause}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]

        # 查询分页数据
        offset = (page - 1) * page_size
        data_sql = f"""
            SELECT user_id, affection_score, last_level, total_interactions, last_interact_at
            FROM user_affection
            {where_clause}
            ORDER BY affection_score DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(data_sql, params + [page_size, offset])
        rows = cursor.fetchall()

        conn.close()

        # 转换为字典列表
        items = []
        for row in rows:
            items.append({
                "user_id": row[0],
                "score": round(row[1], 2),
                "level": row[2],
                "level_name": self.level_to_name(row[2]),
                "total_interactions": row[3],
                "last_interact_at": row[4] or ""
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def admin_update_score(self, user_id: str, new_score: float) -> dict:
        """
        管理员手动修改好感度分数

        Args:
            user_id: 用户 ID
            new_score: 新分数（会被限制在 0.1-10.0）

        Returns:
            更新后的用户数据
        """
        return await asyncio.to_thread(
            self._admin_update_score_sync, user_id, new_score
        )

    def _admin_update_score_sync(self, user_id: str, new_score: float) -> dict:
        """同步版本的管理员修改"""
        # 限制分数范围（0.0 到 13.0）
        new_score = max(0.0, min(13.0, new_score))
        new_level = self.score_to_level(new_score)

        conn = self._get_connection()
        cursor = conn.cursor()

        # 检查用户是否存在
        cursor.execute(
            "SELECT user_id FROM user_affection WHERE user_id = ?",
            (user_id,)
        )
        if cursor.fetchone() is None:
            conn.close()
            return {"error": "用户不存在"}

        # 更新分数
        cursor.execute(
            """UPDATE user_affection
               SET affection_score = ?, last_level = ?
               WHERE user_id = ?""",
            (new_score, new_level, user_id)
        )
        conn.commit()

        # 返回更新后的数据
        cursor.execute(
            """SELECT user_id, affection_score, last_level, total_interactions, last_interact_at
               FROM user_affection WHERE user_id = ?""",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()

        logger.info(f"🔧 管理员修改好感度: user={user_id}, score={new_score}, level={new_level}")

        return {
            "user_id": row[0],
            "score": round(row[1], 2),
            "level": row[2],
            "level_name": self.level_to_name(row[2]),
            "total_interactions": row[3],
            "last_interact_at": row[4] or ""
        }


# === 单例获取函数 ===

_affection_service: Optional[AffectionService] = None


def get_affection_service() -> AffectionService:
    """获取好感度服务单例"""
    global _affection_service
    if _affection_service is None:
        _affection_service = AffectionService()
    return _affection_service
