"""
歌词总结服务
调用推理模型生成歌词总结
"""
from typing import Optional
from src.core.config_manager import ConfigManager
from src.services.ai_manager import AIManager
from src.core.logger import logger


class LyricsSummarizer:
    """歌词总结器"""
    
    @staticmethod
    async def summarize(lyrics_text: str) -> Optional[str]:
        """
        生成歌词总结
        
        Args:
            lyrics_text: 清洗后的歌词文本
        
        Returns:
            总结文本（≤180字），失败返回 None
        """
        if not lyrics_text:
            return None
        
        cfg = ConfigManager.get_musictext_config()
        ai_cfg = ConfigManager.get_ai_config()
        
        # 构造提示词
        prompt_template = cfg.prompt.template
        max_chars = cfg.general.max_chars
        system_prompt = prompt_template.format(max_chars=max_chars)
        
        # 构造消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": lyrics_text}
        ]
        
        # 调用推理模型（使用 utility 工具类模型，如果没有则用 organizer）
        try:
            logger.info("🎵 开始生成歌词总结...")
            
            # 获取 utility 配置（如果没有则用 organizer）
            utility_cfg = getattr(ai_cfg, 'utility', None) or ai_cfg.organizer
            provider_name = utility_cfg.provider or ai_cfg.common.default_provider
            provider_cfg = ai_cfg.providers.get(provider_name)
            
            if not provider_cfg:
                logger.error(f"未找到供应商配置: {provider_name}")
                return None
            
            logger.debug(f"使用模型: {utility_cfg.model_name}, 供应商: {provider_name}")
            logger.debug(f"歌词长度: {len(lyrics_text)} 字符")
            
            # 直接调用 HTTP 客户端
            from src.services.http_client import AsyncHTTPClient
            from src.models.api_types import ChatMessage
            
            chat_messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=lyrics_text)
            ]
            
            async with AsyncHTTPClient(timeout=utility_cfg.timeout) as client:
                response = await client.chat_completion(
                    api_base=provider_cfg.api_base,
                    api_key=provider_cfg.api_key,
                    model=utility_cfg.model_name,
                    messages=chat_messages,
                    temperature=utility_cfg.temperature,
                    max_tokens=utility_cfg.max_tokens,
                    timeout=utility_cfg.timeout
                )
            
            if not response:
                logger.error("模型返回空响应")
                return None
            
            logger.debug(f"模型响应类型: {type(response)}")
            
            # 提取总结文本
            summary = AsyncHTTPClient.parse_completion_response(response)
            
            if not summary:
                logger.error("无法从响应中提取总结文本")
                return None
            
            logger.info(f"✅ 总结生成成功，长度: {len(summary)} 字符")
            
            # 硬性截断兜底（确保不超过 max_chars）
            summary = summary.strip()
            if len(summary) > max_chars:
                summary = summary[:max_chars]
            
            return summary
            
        except Exception as e:
            logger.error(f"生成歌词总结失败: {e}", exc_info=True)
            return None


# 全局单例
lyrics_summarizer = LyricsSummarizer()
