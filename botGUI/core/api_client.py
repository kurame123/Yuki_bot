"""
API 客户端 - 调用 Bot 的 FastAPI 接口
"""
import json
from typing import Any, Optional
from dataclasses import dataclass
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


@dataclass
class APIResponse:
    """API 响应"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class APIClient:
    """Bot Web API 客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = 5.0
    
    def set_base_url(self, url: str):
        """设置 API 基础 URL"""
        self._base_url = url.rstrip("/")
    
    def set_token(self, token: str):
        """设置认证 Token"""
        self._token = token
    
    def _request(self, method: str, path: str, data: Optional[dict] = None) -> APIResponse:
        """发送 HTTP 请求"""
        url = f"{self._base_url}{path}"
        if self._token:
            url += f"?token={self._token}" if "?" not in url else f"&token={self._token}"
        
        try:
            headers = {"Content-Type": "application/json"}
            body = json.dumps(data).encode() if data else None
            
            req = Request(url, data=body, headers=headers, method=method)
            
            with urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode())
                return APIResponse(
                    success=result.get("success", True),
                    data=result.get("data"),
                    error=result.get("error")
                )
        
        except HTTPError as e:
            return APIResponse(success=False, error=f"HTTP {e.code}: {e.reason}")
        except URLError as e:
            return APIResponse(success=False, error=f"连接失败: {e.reason}")
        except json.JSONDecodeError:
            return APIResponse(success=False, error="响应解析失败")
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    def ping(self) -> bool:
        """检查 Bot 是否在线"""
        resp = self._request("GET", "/admin/api/stats")
        return resp.success
    
    def get_stats(self) -> APIResponse:
        """获取统计数据"""
        return self._request("GET", "/admin/api/stats")
    
    def get_config(self) -> APIResponse:
        """获取配置概览"""
        return self._request("GET", "/admin/api/config")
    
    def get_affection_overview(self) -> APIResponse:
        """获取好感度总览"""
        return self._request("GET", "/admin/api/affection/overview")
    
    def get_affection_list(self, page: int = 1, page_size: int = 20) -> APIResponse:
        """获取好感度用户列表"""
        return self._request("GET", f"/admin/api/affection/list?page={page}&page_size={page_size}")
    
    def update_affection(self, user_id: str, score: float) -> APIResponse:
        """更新用户好感度"""
        return self._request("POST", "/admin/api/affection/update", {
            "user_id": user_id,
            "score": score
        })
    
    def get_db_files(self) -> APIResponse:
        """获取数据库文件列表"""
        return self._request("GET", "/admin/api/db/files")
    
    def get_db_tables(self, db: str) -> APIResponse:
        """获取数据库表列表"""
        return self._request("GET", f"/admin/api/db/tables?db={db}")
    
    def get_table_data(self, db: str, table: str, page: int = 1) -> APIResponse:
        """获取表数据"""
        return self._request("GET", f"/admin/api/db/table?db={db}&table={table}&page={page}")
    
    def run_query(self, db: str, sql: str) -> APIResponse:
        """执行 SQL 查询"""
        return self._request("POST", "/admin/api/db/query", {"db": db, "sql": sql})


def get_api_client(port: int = 8080, token: str = "") -> APIClient:
    """获取 API 客户端"""
    return APIClient(f"http://127.0.0.1:{port}", token)
