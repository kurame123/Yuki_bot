"""
Web 后台路由定义
"""
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from src.services.stats_service import get_stats_service
from src.core.Affection import get_affection_service
from src.core.db_browser import (
    list_databases, list_tables, fetch_table_rows, run_select_query
)
from src.core.logger import logger

# 创建路由器 - 不带 prefix，根路径和 /admin 都能访问
router = APIRouter(tags=["admin"])

# 根路径路由器 - 用于重定向
root_router = APIRouter()

# Web 模块目录
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# 配置缓存
_web_config = None


def get_web_config():
    """获取 Web 配置"""
    global _web_config
    if _web_config is None:
        try:
            import tomli
            config_path = Path("configs/web_config.toml")
            if config_path.exists():
                with open(config_path, "rb") as f:
                    _web_config = tomli.load(f)
            else:
                _web_config = {
                    "server": {"access_token": "yuki-admin-2024", "enabled": True},
                    "ui": {"title": "Yuki Bot 控制台"},
                    "stats": {"refresh_interval": 5}
                }
        except Exception as e:
            logger.error(f"Failed to load web config: {e}")
            _web_config = {"server": {"access_token": "", "enabled": True}}
    return _web_config


def verify_token(request: Request) -> bool:
    """验证访问 Token"""
    config = get_web_config()
    expected_token = config.get("server", {}).get("access_token", "")
    
    if not expected_token:
        return True  # 未配置 token 则不验证
    
    # 从 query 参数获取
    token = request.query_params.get("token", "")
    if token == expected_token:
        return True
    
    # 从 Header 获取
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == expected_token:
            return True
    
    return False


async def check_auth(request: Request):
    """依赖注入：检查认证"""
    if not verify_token(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


# 根路径：重定向到 /admin
@root_router.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root_redirect():
    """根路径重定向到管理面板"""
    return RedirectResponse(url="/admin")


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/", response_class=HTMLResponse)
async def dashboard(request: Request, _: None = Depends(check_auth)):
    """返回管理后台页面"""
    template_path = TEMPLATES_DIR / "dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard template not found</h1>", status_code=500)


@router.get("/admin/api/stats")
async def get_stats(request: Request, _: None = Depends(check_auth)):
    """获取统计数据 API"""
    try:
        stats_service = get_stats_service()
        global_stats = stats_service.get_global_stats()
        today_stats = stats_service.get_today_stats()
        daily_stats = stats_service.get_daily_stats(days=7)
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "global": global_stats,
                "today": today_stats,
                "daily": daily_stats,
            }
        })
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/admin/api/config")
async def get_config(request: Request, _: None = Depends(check_auth)):
    """获取配置概览 API"""
    try:
        from src.core.config_manager import ConfigManager

        bot_config = ConfigManager.get_bot_config()
        ai_config = ConfigManager.get_ai_config()

        # 兼容不同的白名单字段名
        whitelist = bot_config.whitelist
        user_count = len(getattr(whitelist, 'allowed_users', []) or getattr(whitelist, 'users', []))
        group_count = len(getattr(whitelist, 'allowed_groups', []) or getattr(whitelist, 'groups', []))

        return JSONResponse(content={
            "success": True,
            "data": {
                "bot_nickname": bot_config.nickname,
                "organizer_model": ai_config.organizer.model_name,
                "generator_model": ai_config.generator.model_name,
                "whitelist_count": user_count + group_count,
            }
        })
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


# ============ 好感度管理页面和 API ============

@router.get("/admin/affection", response_class=HTMLResponse)
@router.get("/admin/affection/", response_class=HTMLResponse)
async def affection_page(request: Request, _: None = Depends(check_auth)):
    """好感度管理页面"""
    template_path = TEMPLATES_DIR / "affection.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Affection template not found</h1>", status_code=500)


@router.get("/admin/api/affection/overview")
async def affection_overview(request: Request, _: None = Depends(check_auth)):
    """好感度总览统计 API"""
    try:
        affection_service = get_affection_service()
        data = await affection_service.get_overview()
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        logger.error(f"Failed to get affection overview: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/admin/api/affection/list")
async def affection_list(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    level: Optional[int] = None,
    keyword: Optional[str] = None,
    _: None = Depends(check_auth)
):
    """好感度用户列表 API"""
    try:
        affection_service = get_affection_service()
        data = await affection_service.list_users(page, page_size, level, keyword)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        logger.error(f"Failed to get affection list: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.post("/admin/api/affection/update")
async def affection_update(request: Request, _: None = Depends(check_auth)):
    """管理员修改好感度 API"""
    try:
        body = await request.json()
        user_id = body.get("user_id")
        score = body.get("score")

        if not user_id or score is None:
            return JSONResponse(
                content={"success": False, "error": "缺少 user_id 或 score"},
                status_code=400
            )

        affection_service = get_affection_service()
        data = await affection_service.admin_update_score(user_id, float(score))

        if "error" in data:
            return JSONResponse(
                content={"success": False, "error": data["error"]},
                status_code=404
            )

        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        logger.error(f"Failed to update affection: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


# ============ SQLite 数据库浏览器页面和 API ============

@router.get("/admin/db", response_class=HTMLResponse)
@router.get("/admin/db/", response_class=HTMLResponse)
async def db_browser_page(request: Request, _: None = Depends(check_auth)):
    """数据库浏览器页面"""
    template_path = TEMPLATES_DIR / "db_browser.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>DB Browser template not found</h1>", status_code=500)


@router.get("/admin/api/db/files")
async def db_list_files(request: Request, _: None = Depends(check_auth)):
    """获取数据库文件列表 API"""
    try:
        databases = list_databases()
        return JSONResponse(content={"success": True, "data": databases})
    except Exception as e:
        logger.error(f"Failed to list databases: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/admin/api/db/tables")
async def db_list_tables(
    request: Request,
    db: str,
    _: None = Depends(check_auth)
):
    """获取数据库表列表 API"""
    try:
        tables = list_tables(db)
        return JSONResponse(content={"success": True, "data": tables})
    except ValueError as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Failed to list tables: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/admin/api/db/table")
async def db_fetch_table(
    request: Request,
    db: str,
    table: str,
    page: int = 1,
    page_size: int = 20,
    _: None = Depends(check_auth)
):
    """获取表数据 API"""
    try:
        data = fetch_table_rows(db, table, page, page_size)
        return JSONResponse(content={"success": True, "data": data})
    except ValueError as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Failed to fetch table data: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.post("/admin/api/db/query")
async def db_run_query(request: Request, _: None = Depends(check_auth)):
    """执行 SQL 查询 API（只允许 SELECT）"""
    try:
        body = await request.json()
        db = body.get("db")
        sql = body.get("sql")

        if not db or not sql:
            return JSONResponse(
                content={"success": False, "error": "缺少 db 或 sql 参数"},
                status_code=400
            )

        data = run_select_query(db, sql)
        return JSONResponse(content={"success": True, "data": data})
    except ValueError as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Failed to run query: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


def setup_web_routes(app):
    """
    设置 Web 路由
    
    Args:
        app: FastAPI 应用实例
    """
    config = get_web_config()
    if not config.get("server", {}).get("enabled", True):
        logger.info("Web admin is disabled in config")
        return
    
    # 确保静态文件目录存在
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(exist_ok=True)
    (STATIC_DIR / "js").mkdir(exist_ok=True)
    (STATIC_DIR / "images").mkdir(exist_ok=True)
    
    # 挂载静态文件
    app.mount("/admin/static", StaticFiles(directory=str(STATIC_DIR)), name="admin_static")
    
    # 注册路由
    app.include_router(root_router)  # 根路径重定向
    app.include_router(router)       # 管理面板路由
    
    logger.info("✅ Web admin routes registered at / and /admin")


# ============ 知识图谱可视化页面和 API ============

@router.get("/admin/graph", response_class=HTMLResponse)
@router.get("/admin/graph/", response_class=HTMLResponse)
async def knowledge_graph_page(request: Request, _: None = Depends(check_auth)):
    """知识图谱可视化页面"""
    template_path = TEMPLATES_DIR / "knowledge_graph.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Knowledge Graph template not found</h1>", status_code=500)


@router.get("/admin/api/graph/stats")
async def graph_stats(request: Request, _: None = Depends(check_auth)):
    """知识图谱统计信息 API"""
    try:
        from src.core.RAGM.graph_storage import get_graph_storage
        storage = get_graph_storage()
        
        stats = storage.get_stats()
        
        return JSONResponse(content={"success": True, "data": stats})
    except Exception as e:
        logger.error(f"Failed to get graph stats: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/admin/api/graph/users")
async def graph_users(request: Request, _: None = Depends(check_auth)):
    """获取图谱中的用户列表 API"""
    try:
        from src.core.RAGM.graph_storage import get_graph_storage
        storage = get_graph_storage()
        
        users = storage.get_users()
        
        return JSONResponse(content={"success": True, "data": users})
    except Exception as e:
        logger.error(f"Failed to get graph users: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/admin/api/graph/data")
async def graph_data(
    request: Request,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    search: Optional[str] = None,
    _: None = Depends(check_auth)
):
    """获取图谱数据 API（节点和边）"""
    try:
        from src.core.RAGM.graph_storage import get_graph_storage
        storage = get_graph_storage()
        
        data = storage.get_graph_data(user_id, entity_type, search)
        
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        logger.error(f"Failed to get graph data: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.post("/admin/api/graph/clear")
async def graph_clear(request: Request, _: None = Depends(check_auth)):
    """清空知识图谱 API"""
    try:
        body = await request.json()
        user_id = body.get("user_id")
        
        from src.core.RAGM.graph_storage import get_graph_storage
        storage = get_graph_storage()
        
        if user_id:
            count = storage.clear_user_graph(user_id)
            message = f"已清空用户 {user_id} 的图谱（{count} 个节点）"
        else:
            count = storage.clear_all_graph()
            message = f"已清空所有图谱（{count} 个节点）"
        
        return JSONResponse(content={"success": True, "message": message, "count": count})
    except Exception as e:
        logger.error(f"Failed to clear graph: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )
