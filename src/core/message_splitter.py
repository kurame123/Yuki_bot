"""
LLM 驱动的消息拆分器 - Message Splitter
使用 LLM 智能拆分长文本，保持自然语言习惯
"""
import asyncio
import random
from typing import List, AsyncGenerator, Optional
from src.core.config_manager import ConfigManager
from src.core.logger import logger
from src.services.http_client import AsyncHTTPClient
from src.models.api_types import ChatMessage


class MessageSplitter:
    """
    LLM 驱动的消息拆分工具
    
    核心逻辑：
    1. 使用 LLM 智能拆分：保持语义完整性
    2. 拟人延迟：发送间隔模拟打字时间
    3. 特殊保护：代码块等特殊内容不拆分
    """

    def __init__(self):
        """初始化拆分器，从配置加载参数"""
        self._load_config()
        logger.info("✅ Message Splitter initialized (LLM-powered)")
    
    def _load_config(self) -> None:
        """从配置文件加载参数"""
        try:
            bot_config = ConfigManager.get_bot_config()
            strategy = bot_config.reply_strategy
            
            self.enabled = strategy.enable_split
            self.split_threshold = strategy.split_threshold
            self.min_segment_length = strategy.min_segment_length
            self.typing_speed = strategy.typing_speed
            self.max_delay = strategy.max_delay
            
            logger.debug(
                f"Reply strategy config loaded: "
                f"enabled={self.enabled}, threshold={self.split_threshold}"
            )
        except Exception as e:
            logger.warning(f"Failed to load config, using defaults: {e}")
            self.enabled = True
            self.split_threshold = 50
            self.min_segment_length = 5
            self.typing_speed = 0.15
            self.max_delay = 5.0

    async def split_text(self, text: str) -> List[str]:
        """
        使用 LLM 智能拆分文本
        
        Args:
            text: 原始文本
            
        Returns:
            拆分后的句子列表
        """
        # 1. 检查是否需要拆分
        if not self.enabled or len(text) < self.split_threshold:
            return [text]
        
        # 2. 检查是否包含代码块，如果有则不拆分
        if "```" in text:
            logger.debug("Text contains code block, skip splitting")
            return [text]
        
        # 3. 使用 LLM 拆分
        try:
            segments = await self._llm_split(text)
            if segments and len(segments) > 0:
                logger.debug(f"LLM split text into {len(segments)} segments")
                return segments
            else:
                logger.warning("LLM split failed, return original text")
                return [text]
        except Exception as e:
            logger.error(f"LLM split error: {e}, return original text")
            return [text]

    async def _llm_split(self, text: str) -> List[str]:
        """
        调用 LLM 进行智能拆分
        
        Args:
            text: 原始文本
            
        Returns:
            拆分后的句子列表
        """
        try:
            ai_config = ConfigManager.get_ai_config()
            utility = ai_config.utility
            
            if not utility:
                logger.warning("Utility model not configured, fallback to simple split")
                return [text]
            
            # 构建提示词
            system_prompt = """你是消息拆分助手。将长文本拆分成多条短消息，模拟真人发送消息的习惯。

【拆分规则】
1. 根据长度进行拆分，可以选择不拆，不拆则直接原文返回
2. 保持语义完整，不要在句子中间断开
3. 不要添加任何标点符号，保持原文
4. 不要添加序号、分隔符等额外内容

【输出格式】
每行一条消息，不要有空行，不要有序号。

【示例】
输入：随你吧，反正说了你也不信，都一点了啊，你还不睡吗
输出：
随你吧
反正说了你也不信
都一点了啊
你还不睡吗"""

            user_prompt = f"请拆分以下文本：\n{text}"
            
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt)
            ]
            
            # 获取供应商配置
            provider_name = getattr(utility, 'provider', '') or ai_config.common.default_provider
            providers = getattr(ai_config, 'providers', {})
            
            if provider_name in providers:
                provider = providers[provider_name]
                api_base = provider.api_base
                api_key = provider.api_key
                timeout = provider.timeout
            else:
                logger.warning(f"Provider {provider_name} not found")
                return [text]
            
            # 调用模型
            async with AsyncHTTPClient(timeout=timeout) as client:
                response = await client.chat_completion(
                    api_base=api_base,
                    api_key=api_key,
                    model=utility.model_name,
                    messages=messages,
                    temperature=0.3,  # 低温度保证稳定输出
                    max_tokens=500,
                    timeout=timeout
                )
            
            result = AsyncHTTPClient.parse_completion_response(response)
            
            if not result:
                return [text]
            
            # 解析结果：按行分割
            segments = [line.strip() for line in result.strip().split('\n') if line.strip()]
            
            # 过滤掉序号（如 "1. "）
            import re
            segments = [re.sub(r'^\d+[.、]\s*', '', seg) for seg in segments]
            
            # 验证拆分结果
            if not segments or len(segments) == 0:
                return [text]
            
            return segments
            
        except Exception as e:
            logger.error(f"LLM split failed: {e}")
            return [text]

    async def process_and_send(
        self,
        text: str,
        send_func,
        user_name: str = "用户"
    ) -> None:
        """
        异步处理并发送：拆分文本，在每段之间增加拟人化的等待时间
        
        Args:
            text: 要发送的文本
            send_func: 发送函数（async），接收一个字符串参数
            user_name: 用户名称（用于日志）
        """
        segments = await self.split_text(text)
        logger.info(f"📨 [{user_name}] process_and_send: 拆分成 {len(segments)} 段")
        
        if not segments:
            return
        
        for i, segment in enumerate(segments):
            if not segment:
                continue
            
            # 发送当前段落
            logger.info(f"📤 [{user_name}] 发送第{i+1}/{len(segments)}段（{len(segment)}字）: {segment[:40]}")
            await send_func(segment)
            logger.info(f"✅ [{user_name}] 第{i+1}段已发送")
            
            # 如果不是最后一段，增加等待时间
            if i < len(segments) - 1:
                delay = self._calculate_delay(segment)
                logger.info(f"⏳ [{user_name}] 等待 {delay:.2f}s")
                await asyncio.sleep(delay)

    async def process_and_wait(self, text: str) -> AsyncGenerator[str, None]:
        """
        异步生成器：在每段文本之间增加拟人化的等待时间
        
        用法示例：
            async for segment in splitter.process_and_wait(text):
                await bot.send(segment)
        
        Args:
            text: 要处理的文本
            
        Yields:
            拆分后的每一段文本
        """
        segments = await self.split_text(text)
        
        for i, segment in enumerate(segments):
            yield segment
            
            # 如果不是最后一段，需要等待
            if i < len(segments) - 1:
                delay = self._calculate_delay(segment)
                await asyncio.sleep(delay)

    def _calculate_delay(self, segment: str) -> float:
        """
        计算合理的延迟时间
        
        基于以下因素：
        - 当前段落的字数
        - 打字速度
        - 随机波动（更像真人）
        
        Args:
            segment: 当前段落
            
        Returns:
            延迟时间（秒）
        """
        # 基础延迟 = 字数 * 打字速度
        base_delay = len(segment) * self.typing_speed
        
        # 增加随机波动（0.8 ~ 1.2 倍）以显得更自然
        jitter = random.uniform(0.8, 1.2)
        final_delay = base_delay * jitter
        
        # 不超过最大延迟上限
        return min(final_delay, self.max_delay)


# 全局单例
_message_splitter: Optional[MessageSplitter] = None


def get_message_splitter() -> MessageSplitter:
    """获取全局消息拆分器单例"""
    global _message_splitter
    if _message_splitter is None:
        _message_splitter = MessageSplitter()
    return _message_splitter


def reset_message_splitter() -> None:
    """重置消息拆分器单例（用于热重载配置）"""
    global _message_splitter
    _message_splitter = None
    logger.info("✅ Message Splitter 已重置，下次使用时将重新加载配置")
