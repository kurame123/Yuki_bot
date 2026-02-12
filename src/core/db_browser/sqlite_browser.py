"""
SQLite 数据库浏览器服务
提供只读的数据库浏览功能，用于 Web 管理后台
"""
import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.core.logger import logger

# 配置：允许浏览的目录
BASE_DIRS = ["./data"]
MAX_PAGE_SIZE = 200
ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}

# 危险关键词（禁止执行）
DANGEROUS_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "VACUUM", "REINDEX"
]


def list_databases() -> List[Dict[str, str]]:
    """
    列出所有可浏览的数据库文件
    
    Returns:
        [{"name": "affection.db", "path": "data/affection.db"}, ...]
    """
    databases = []
    
    for base_dir in BASE_DIRS:
        base_path = Path(base_dir)
        if not base_path.exists():
            continue
        
        # 递归查找所有数据库文件
        for ext in ALLOWED_EXTENSIONS:
            for db_file in base_path.rglob(f"*{ext}"):
                if db_file.is_file():
                    rel_path = str(db_file).replace("\\", "/")
                    databases.append({
                        "name": db_file.name,
                        "path": rel_path,
                        "size": _format_size(db_file.stat().st_size)
                    })
    
    # 按名称排序
    databases.sort(key=lambda x: x["name"])
    return databases


def _format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def validate_db_path(rel_path: str) -> Path:
    """
    验证数据库路径是否在允许的目录内（防止目录穿越攻击）
    
    Args:
        rel_path: 相对路径，如 "data/affection.db"
        
    Returns:
        验证通过的绝对路径
        
    Raises:
        ValueError: 路径不合法或不在允许目录内
    """
    # 规范化路径
    target_path = Path(rel_path).resolve()
    
    # 检查是否在允许的目录内
    for base_dir in BASE_DIRS:
        base_path = Path(base_dir).resolve()
        try:
            target_path.relative_to(base_path)
            # 检查文件存在且是数据库文件
            if target_path.exists() and target_path.suffix.lower() in ALLOWED_EXTENSIONS:
                return target_path
        except ValueError:
            continue
    
    raise ValueError(f"路径不在允许的目录内或文件不存在: {rel_path}")


def list_tables(db_rel_path: str) -> List[Dict[str, Any]]:
    """
    列出数据库中的所有表
    
    Args:
        db_rel_path: 数据库相对路径
        
    Returns:
        [{"name": "user_affection", "rows": 123}, ...]
    """
    db_path = validate_db_path(db_rel_path)
    tables = []
    
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # 获取所有表名
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [row[0] for row in cursor.fetchall()]
        
        # 统计每张表的行数
        for table_name in table_names:
            # 跳过 sqlite 内部表
            if table_name.startswith("sqlite_"):
                continue
            
            try:
                # 安全地获取行数（表名用双引号包裹）
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                row_count = cursor.fetchone()[0]
                tables.append({
                    "name": table_name,
                    "rows": row_count
                })
            except sqlite3.Error as e:
                logger.warning(f"无法统计表 {table_name} 的行数: {e}")
                tables.append({
                    "name": table_name,
                    "rows": -1  # 表示无法统计
                })
    finally:
        conn.close()
    
    return tables


def fetch_table_rows(
    db_rel_path: str,
    table: str,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """
    分页获取表数据
    
    Args:
        db_rel_path: 数据库相对路径
        table: 表名
        page: 页码（从 1 开始）
        page_size: 每页行数
        
    Returns:
        {
            "columns": ["id", "user_id", ...],
            "rows": [[1, "123456", ...], ...],
            "page": 1,
            "page_size": 20,
            "total": 123
        }
    """
    db_path = validate_db_path(db_rel_path)
    
    # 限制 page_size
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size
    
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # 验证表名存在（防止 SQL 注入）
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        if cursor.fetchone() is None:
            raise ValueError(f"表不存在: {table}")
        
        # 获取总行数
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        total = cursor.fetchone()[0]
        
        # 获取分页数据
        cursor.execute(f'SELECT * FROM "{table}" LIMIT ? OFFSET ?', (page_size, offset))
        rows = cursor.fetchall()
        
        # 获取列名
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total
        }
    finally:
        conn.close()


def run_select_query(
    db_rel_path: str,
    sql: str,
    limit_override: Optional[int] = None
) -> Dict[str, Any]:
    """
    执行只读 SELECT 查询
    
    Args:
        db_rel_path: 数据库相对路径
        sql: SQL 查询语句（只允许 SELECT）
        limit_override: 强制限制返回行数
        
    Returns:
        {
            "columns": [...],
            "rows": [...],
            "row_count": 实际返回行数
        }
        
    Raises:
        ValueError: SQL 不合法或包含危险操作
    """
    db_path = validate_db_path(db_rel_path)
    
    # 清理和验证 SQL
    sql = sql.strip()
    sql_upper = sql.upper()
    
    # 必须以 SELECT 开头
    if not sql_upper.startswith("SELECT"):
        raise ValueError("只允许执行 SELECT 查询")
    
    # 检查是否包含多条语句
    if ";" in sql[:-1]:  # 允许末尾的分号
        raise ValueError("不允许执行多条 SQL 语句")
    
    # 检查危险关键词
    for keyword in DANGEROUS_KEYWORDS:
        # 使用单词边界匹配，避免误判（如 "SELECTED"）
        if re.search(rf"\b{keyword}\b", sql_upper):
            raise ValueError(f"SQL 包含不允许的操作: {keyword}")
    
    # 如果没有 LIMIT，自动添加
    if "LIMIT" not in sql_upper:
        limit = limit_override or MAX_PAGE_SIZE
        sql = sql.rstrip(";") + f" LIMIT {limit}"
    
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows)
        }
    except sqlite3.Error as e:
        raise ValueError(f"SQL 执行错误: {str(e)}")
    finally:
        conn.close()
