"""
异步 HTTP 客户端封装
用于请求 OpenAI 格式的 API
"""
import httpx
import json
from typing import Dict, Any, Optional, List
from src.core.logger import logger
from src.models.api_types import ChatMessage, ChatRequest, ChatResponse


class AsyncHTTPClient:
    """
    异步 HTTP 客户端，封装对 OpenAI 格式 API 的请求
    """
    
    def __init__(self, timeout: int = 30):
        """
        初始化客户端
        
        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """上下文管理器入口"""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        if self.client:
            await self.client.aclose()
    
    async def chat_completion(
        self,
        api_base: str,
        api_key: str,
        model: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送聊天完成请求到 OpenAI 兼容 API
        
        Args:
            api_base: API 基础 URL（如 https://api.openai.com/v1）
            api_key: API 密钥
            model: 模型名称
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            timeout: 超时时间（覆盖默认值）
            
        Returns:
            API 响应（字典格式）
            
        Raises:
            httpx.RequestError: 网络请求错误
            httpx.HTTPStatusError: HTTP 状态错误
        """
        if not self.client:
            raise RuntimeError("请使用 'async with' 管理器使用此客户端")
        
        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [msg.dict() for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        logger.debug(f"发送请求到 {url}")
        logger.debug(f"  模型: {model}")
        logger.debug(f"  消息数: {len(messages)}")
        
        try:
            response = await self.client.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout or self.timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"✅ API请求成功，耗时: {response.elapsed.total_seconds():.2f}秒")
            return result
            
        except httpx.TimeoutException as e:
            logger.error(f"❌ API 请求超时（{timeout or self.timeout}秒）: {url}")
            logger.error(f"   模型: {model}, 消息数: {len(messages)}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ API 返回错误 {e.response.status_code}: {e.response.text[:200]}")
            logger.error(f"   URL: {url}, 模型: {model}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ API 请求失败: {type(e).__name__}: {e}")
            logger.error(f"   URL: {url}, 模型: {model}")
            raise
    
    @staticmethod
    def parse_completion_response(response: Dict[str, Any]) -> str:
        """
        解析 OpenAI 格式的完成响应
        
        Args:
            response: API 响应字典
            
        Returns:
            提取的回复文本
        """
        try:
            # 标准 OpenAI 格式
            content = ""
            if "choices" in response and len(response["choices"]) > 0:
                first_choice = response["choices"][0]
                if "message" in first_choice:
                    content = first_choice["message"]["content"]
                elif "text" in first_choice:
                    content = first_choice["text"]
            
            if not content:
                logger.error(f"无法解析响应: {response}")
                return ""
            
            # 过滤 <think>...</think> 标签（DeepSeek-V3 等模型可能输出）
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            
            return content
            
        except (KeyError, IndexError) as e:
            logger.error(f"解析响应时出错: {e}")
            return ""
    
    @staticmethod
    def parse_reasoning_content(response: Dict[str, Any]) -> str:
        """
        解析推理模型的思考过程（reasoning_content）
        
        适用于 DeepSeek-R1 等支持推理的模型
        
        Args:
            response: API 响应字典
            
        Returns:
            思考过程文本，如果不存在则返回空字符串
        """
        try:
            if "choices" in response and len(response["choices"]) > 0:
                first_choice = response["choices"][0]
                if "message" in first_choice:
                    # DeepSeek-R1 格式：reasoning_content 在 message 中
                    return first_choice["message"].get("reasoning_content", "")
            return ""
        except (KeyError, IndexError) as e:
            logger.debug(f"解析 reasoning_content 时出错: {e}")
            return ""
    
    @staticmethod
    def parse_usage(response: Dict[str, Any]) -> Dict[str, int]:
        """
        解析 API 响应中的 token 使用量
        
        Args:
            response: API 响应字典
            
        Returns:
            包含 prompt_tokens 和 completion_tokens 的字典
        """
        try:
            usage = response.get("usage", {})
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        except Exception as e:
            logger.warning(f"解析 usage 时出错: {e}")
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
