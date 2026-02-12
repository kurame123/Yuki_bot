"""
图片描述服务 - 将图片转换为自然语言描述，用于参与对话和记忆

职责：
1. 接收图片 URL
2. 本地下载图片并转为 base64（避免视觉 API 访问 QQ CDN 超时）
3. 调用视觉模型生成简短客观的描述
4. 返回可直接参与对话的文本

使用场景：
- 用户发送图片时，将图片内容"翻译"成文字
- 描述文本会被当作用户消息的一部分，进入对话流、记忆系统和向量数据库
"""
import re
import base64
import httpx
from typing import Optional, Tuple

from src.core.config_manager import ConfigManager
from src.core.logger import logger


class VisionCaptionService:
    """图片描述服务"""
    
    _instance: Optional['VisionCaptionService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.ai_config = None
        self._refresh_config()
        logger.info("✅ 图片描述服务初始化成功")
    
    def _refresh_config(self) -> None:
        """刷新配置"""
        try:
            self.ai_config = ConfigManager.get_ai_config()
        except RuntimeError:
            logger.warning("配置未加载，请先调用 ConfigManager.load()")
    
    def _get_provider_config(self, provider_name: str = None) -> tuple:
        """获取供应商配置"""
        if not self.ai_config:
            self._refresh_config()
        
        providers = self.ai_config.providers
        if not provider_name:
            provider_name = self.ai_config.common.default_provider
        
        if provider_name in providers:
            provider = providers[provider_name]
            return provider.api_base, provider.api_key, provider.timeout
        
        raise ValueError(f"未找到供应商配置: {provider_name}")
    
    @property
    def enabled(self) -> bool:
        """检查是否启用图片描述功能"""
        if not self.ai_config:
            self._refresh_config()
        
        caption_config = getattr(self.ai_config, 'vision_caption', None)
        if caption_config:
            return getattr(caption_config, 'enabled', True)
        return True  # 默认启用
    
    def _clean_description(self, text: str, max_length: int = 80) -> str:
        """
        清洗描述文本
        
        - 去掉常见前缀（如"这张图片中…"、"图片显示…"）
        - 控制长度
        """
        if not text:
            return ""
        
        text = text.strip()
        
        # 去掉常见前缀
        prefixes_to_remove = [
            r'^这张图片(中|里|显示|展示)?[，,：:]?\s*',
            r'^图片(中|里|显示|展示)?[，,：:]?\s*',
            r'^画面(中|里|显示|展示)?[，,：:]?\s*',
            r'^图中[，,：:]?\s*',
        ]
        
        for pattern in prefixes_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # 控制长度
        if len(text) > max_length:
            # 尝试在句号处截断
            for sep in ['。', '！', '？', '，', ',']:
                last_sep = text[:max_length].rfind(sep)
                if last_sep > 20:  # 至少保留20字
                    text = text[:last_sep + 1]
                    break
            else:
                # 硬截断并加省略号
                text = text[:max_length - 1] + "…"
        
        return text

    async def _download_image_as_base64(self, url: str, timeout: float = 15) -> Tuple[str, str]:
        """
        下载图片并转为 base64
        
        Args:
            url: 图片 URL
            timeout: 下载超时时间
            
        Returns:
            (base64_data, mime_type) 或 ("", "") 如果失败
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                
                img_bytes = resp.content
                
                # 根据 content-type 或文件头判断图片类型
                content_type = resp.headers.get("content-type", "")
                if "png" in content_type:
                    mime_type = "image/png"
                elif "gif" in content_type:
                    mime_type = "image/gif"
                elif "webp" in content_type:
                    mime_type = "image/webp"
                else:
                    mime_type = "image/jpeg"  # 默认 jpeg
                
                # 转 base64
                b64_data = base64.b64encode(img_bytes).decode("utf-8")
                
                logger.debug(f"📥 图片下载成功: {len(img_bytes)} bytes, {mime_type}")
                return b64_data, mime_type
                
        except httpx.TimeoutException:
            logger.warning(f"⚠️ 图片下载超时: {url[:50]}...")
            return "", ""
        except Exception as e:
            logger.warning(f"⚠️ 图片下载失败: {e}")
            return "", ""

    async def describe_image(self, url: str) -> str:
        """
        调用视觉模型获取图片描述
        
        流程：
        1. 本地下载图片（避免视觉 API 访问 QQ CDN 超时）
        2. 转为 base64
        3. 发送给视觉模型
        
        Args:
            url: 图片 URL
            
        Returns:
            简短客观的图片描述，如：
            "一只趴在书上的猫，看起来有点困。"
            
            如果识别失败返回空字符串
        """
        if not self.enabled:
            logger.debug("图片描述功能已禁用")
            return ""
        
        if not self.ai_config:
            self._refresh_config()
        
        try:
            # 获取配置
            vision_config = self.ai_config.vision
            caption_config = getattr(self.ai_config, 'vision_caption', None)
            
            # 使用 vision_caption 配置，如果没有则回退到 vision 配置
            if caption_config:
                prompt = getattr(caption_config, 'prompt', None) or "请用一句到两句简短自然的中文口语，客观描述这张图片的主要内容和气氛。"
                max_length = getattr(caption_config, 'max_length', 80)
                temperature = getattr(caption_config, 'temperature', 0.3)
                max_tokens = getattr(caption_config, 'max_tokens', 100)
                api_timeout = getattr(caption_config, 'timeout', 30)
            else:
                prompt = "请用一句到两句简短自然的中文口语，客观描述这张图片的主要内容和气氛。"
                max_length = 80
                temperature = vision_config.temperature
                max_tokens = vision_config.max_tokens
                api_timeout = vision_config.timeout
            
            # === 1. 本地下载图片并转 base64 ===
            b64_data, mime_type = await self._download_image_as_base64(url, timeout=15)
            if not b64_data:
                logger.warning(f"⚠️ 无法下载图片，跳过描述: {url[:50]}...")
                return ""
            
            # 构建 data URL
            image_data_url = f"data:{mime_type};base64,{b64_data}"
            
            # === 2. 调用视觉 API ===
            vision_provider = getattr(vision_config, 'provider', '') or None
            api_base, api_key, _ = self._get_provider_config(vision_provider)
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 构建视觉模型请求（使用 base64 而非原始 URL）
            payload = {
                "model": vision_config.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url}
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            async with httpx.AsyncClient(timeout=api_timeout) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    json=payload,
                    headers=headers
                )
                resp.raise_for_status()
                
                result = resp.json()
                raw_description = result['choices'][0]['message']['content'].strip()
                
                # 清洗描述
                description = self._clean_description(raw_description, max_length)
                
                logger.info(f"🖼️ 图片描述: {description}")
                return description
                
        except httpx.TimeoutException:
            logger.warning(f"⚠️ 视觉API超时: {url[:50]}...")
            return ""
        except Exception as e:
            logger.error(f"❌ 图片描述失败: {e}")
            return ""
    
    async def describe_images(self, urls: list) -> list:
        """
        批量描述多张图片
        
        Args:
            urls: 图片 URL 列表
            
        Returns:
            描述列表（与 urls 一一对应，失败的为空字符串）
        """
        import asyncio
        
        if not urls:
            return []
        
        # 并发请求所有图片
        tasks = [self.describe_image(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        descriptions = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"⚠️ 图片描述异常: {r}")
                descriptions.append("")
            else:
                descriptions.append(r or "")
        
        return descriptions


# 全局单例
_vision_caption_service: Optional[VisionCaptionService] = None


def get_vision_caption_service() -> VisionCaptionService:
    """获取全局图片描述服务单例"""
    global _vision_caption_service
    if _vision_caption_service is None:
        _vision_caption_service = VisionCaptionService()
    return _vision_caption_service
