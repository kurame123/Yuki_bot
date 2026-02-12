"""
AI 接口的输入输出类型定义
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# ============ OpenAI 格式的请求/响应类型 ============
class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="消息角色: system/user/assistant")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """OpenAI 格式的聊天请求"""
    model: str = Field(..., description="模型名称")
    messages: List[ChatMessage] = Field(..., description="消息列表")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int = Field(default=2000, description="最大 token 数")
    timeout: int = Field(default=30, description="超时时间")


class ChatResponse(BaseModel):
    """OpenAI 格式的聊天响应"""
    id: str = Field(..., description="响应 ID")
    model: str = Field(..., description="使用的模型")
    choices: List[Dict[str, Any]] = Field(..., description="选择列表")
    usage: Dict[str, int] = Field(..., description="token 使用统计")


# ============ Yuki Bot 内部消息格式 ============
class UserMessage(BaseModel):
    """用户消息"""
    user_id: int = Field(..., description="用户 QQ 号")
    group_id: Optional[int] = Field(None, description="群号（私聊时为 None）")
    content: str = Field(..., description="消息内容")
    timestamp: int = Field(..., description="时间戳")


class BotResponse(BaseModel):
    """机器人响应"""
    content: str = Field(..., description="回复内容")
    user_id: int = Field(..., description="目标用户 ID")
    group_id: Optional[int] = Field(None, description="目标群号")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")
