"""
表情包学习与检索服务
基于哈希去重和向量检索的表情包管理系统

功能：
1. 自动学习：从群聊中收集图片，使用视觉模型生成描述
2. 哈希去重：使用 MD5 避免重复存储
3. 向量检索：基于语义相似度匹配表情包
4. 智能发送：根据对话内容概率性发送相关表情
"""
import os
import hashlib
import base64
import httpx
import aiofiles
from pathlib import Path
from typing import Optional, Tuple
import asyncio

try:
    import chromadb
    from chromadb import Documents, EmbeddingFunction, Embeddings
except ImportError:
    raise ImportError("Please install chromadb: pip install chromadb")

from src.core.config_manager import ConfigManager
from src.core.logger import logger


class SiliconFlowEmbedding(EmbeddingFunction):
    """
    表情包专用嵌入函数（兼容 ChromaDB）
    调用 API 生成向量
    """
    
    def __init__(self):
        ai_config = ConfigManager.get_ai_config()
        embedding_config = ai_config.embedding
        provider_name = getattr(embedding_config, 'provider', '') or ai_config.common.default_provider
        
        providers = getattr(ai_config, 'providers', {})
        if provider_name in providers:
            provider = providers[provider_name]
            self.base_url = provider.api_base
            self.api_key = provider.api_key
            self.timeout = provider.timeout
        else:
            raise ValueError(f"未找到供应商配置: {provider_name}")
        
        self.model = embedding_config.model_name
    
    def __call__(self, input: Documents) -> Embeddings:
        """生成嵌入向量（ChromaDB 接口）"""
        import httpx
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        embeddings = []
        for text in input:
            payload = {
                "model": self.model,
                "input": text,
                "encoding_format": "float"
            }
            
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/embeddings",
                        json=payload,
                        headers=headers
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    
                    if 'data' in result and len(result['data']) > 0:
                        embedding = result['data'][0]['embedding']
                        embeddings.append(embedding)
                    else:
                        # 失败时返回零向量
                        embeddings.append([0.0] * 1024)
            
            except Exception as e:
                logger.error(f"❌ 生成嵌入失败: {e}")
                embeddings.append([0.0] * 1024)
        
        return embeddings


class EmojiService:
    """表情包服务"""
    
    def __init__(self):
        """初始化表情包服务"""
        try:
            bot_config = ConfigManager.get_bot_config()
            ai_config = ConfigManager.get_ai_config()
            
            # 获取配置
            self.emoji_config = bot_config.emoji
            self.ai_config = ai_config
            
            # 确保存储目录存在
            self.save_dir = Path(self.emoji_config.storage_path)
            self.save_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取向量数据库客户端
            db_path = bot_config.storage.vector_db_path
            Path(db_path).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=db_path)
            
            # 创建表情包专用集合
            self.collection = self.client.get_or_create_collection(
                name="emoji_library",
                embedding_function=SiliconFlowEmbedding(),
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"✅ 表情包服务初始化成功")
            logger.info(f"   - 存储路径: {self.save_dir}")
            logger.info(f"   - 学习模式: {'开启' if self.emoji_config.enable_learning else '关闭'}")
            logger.info(f"   - 发送模式: {'开启' if self.emoji_config.enable_sending else '关闭'}")
            logger.info(f"   - 发送概率: {self.emoji_config.sending_probability * 100}%")
            
        except Exception as e:
            logger.error(f"❌ 表情包服务初始化失败: {e}")
            raise
    
    def _calculate_hash(self, content: bytes) -> str:
        """
        计算文件的 MD5 哈希值
        
        Args:
            content: 文件二进制内容
            
        Returns:
            MD5 哈希值（32位十六进制字符串）
        """
        return hashlib.md5(content).hexdigest()
    
    def _get_provider_config(self, provider_name: str = None):
        """获取供应商配置"""
        providers = self.ai_config.providers
        if not provider_name:
            provider_name = self.ai_config.common.default_provider
        
        if provider_name in providers:
            provider = providers[provider_name]
            return provider.api_base, provider.api_key, provider.timeout
        
        # 兼容旧配置
        if hasattr(self.ai_config.common, 'api_base') and self.ai_config.common.api_base:
            return self.ai_config.common.api_base, self.ai_config.common.api_key, self.ai_config.common.timeout
        
        raise ValueError(f"未找到供应商配置: {provider_name}")
    
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
                
                # 根据 content-type 判断图片类型
                content_type = resp.headers.get("content-type", "")
                if "png" in content_type:
                    mime_type = "image/png"
                elif "gif" in content_type:
                    mime_type = "image/gif"
                elif "webp" in content_type:
                    mime_type = "image/webp"
                else:
                    mime_type = "image/jpeg"
                
                b64_data = base64.b64encode(img_bytes).decode("utf-8")
                return b64_data, mime_type
                
        except Exception as e:
            logger.warning(f"⚠️ 图片下载失败: {e}")
            return "", ""

    async def _describe_image(self, img_url: str) -> str:
        """
        调用视觉模型获取图片描述（本地下载 + base64）
        
        Args:
            img_url: 图片 URL
            
        Returns:
            图片描述文本
        """
        try:
            # === 1. 本地下载图片并转 base64 ===
            b64_data, mime_type = await self._download_image_as_base64(img_url, timeout=15)
            if not b64_data:
                logger.warning(f"⚠️ 无法下载图片，跳过识别")
                return ""
            
            image_data_url = f"data:{mime_type};base64,{b64_data}"
            
            # === 2. 调用视觉 API ===
            vision_provider = getattr(self.ai_config.vision, 'provider', '') or None
            api_base, api_key, _ = self._get_provider_config(vision_provider)
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 构建视觉模型请求（使用 base64）
            payload = {
                "model": self.ai_config.vision.model_name,
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
                                "text": "请简短客观地描述这张表情包的内容和情绪。例如：一只流泪的猫、开心大笑的表情、竖起大拇指。不要包含任何解释性文字，只描述画面内容。"
                            }
                        ]
                    }
                ],
                "temperature": self.ai_config.vision.temperature,
                "max_tokens": self.ai_config.vision.max_tokens
            }
            
            async with httpx.AsyncClient(timeout=self.ai_config.vision.timeout) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    json=payload,
                    headers=headers
                )
                resp.raise_for_status()
                
                result = resp.json()
                description = result['choices'][0]['message']['content'].strip()
                
                logger.debug(f"🔍 视觉识别结果: {description}")
                return description
                
        except httpx.TimeoutException:
            logger.warning(f"⚠️ 视觉API超时")
            return ""
        except Exception as e:
            logger.error(f"❌ 视觉模型调用失败: {e}")
            return ""
    
    async def save_emoji(self, url: str) -> bool:
        """
        学习流程：下载 -> 哈希 -> 判重 -> 识别 -> 存储
        
        Args:
            url: 图片 URL
            
        Returns:
            是否成功保存
        """
        # 检查是否启用学习模式
        if not self.emoji_config.enable_learning:
            return False
        
        try:
            # 1. 下载图片数据
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"⚠️  下载图片失败: {url}")
                    return False
                
                img_data = resp.content
            
            # 2. 计算哈希值（作为唯一 ID）
            file_hash = self._calculate_hash(img_data)
            
            # 3. 判重：检查数据库中是否已存在
            existing = self.collection.get(ids=[file_hash])
            if existing['ids']:
                logger.debug(f"♻️  表情已存在，跳过: {file_hash}")
                return False
            
            # 4. 调用视觉模型识别内容
            description = await self._describe_image(url)
            if not description:
                logger.warning(f"⚠️  无法识别图片内容: {url}")
                return False
            
            # 5. 保存文件（文件名为哈希值）
            file_path = self.save_dir / f"{file_hash}.image"
            
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(img_data)
            
            # 6. 存入向量数据库
            self.collection.add(
                documents=[description],              # 向量化的内容：描述文本
                metadatas=[{"path": str(file_path)}], # 元数据：本地路径
                ids=[file_hash]                       # ID：哈希值
            )
            
            logger.info(f"🆕 习得新表情: [{description}] -> {file_hash}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存表情失败: {e}")
            return False
    
    def search_emoji(self, query_text: str) -> Optional[tuple[str, float]]:
        """
        检索表情包
        
        Args:
            query_text: 查询文本（通常是用户的消息）
            
        Returns:
            (表情包文件路径, 相似度) 元组，如果未找到则返回 None
        """
        # 检查是否启用发送模式
        if not self.emoji_config.enable_sending:
            return None
        
        try:
            # 检索最相似的表情
            results = self.collection.query(
                query_texts=[query_text],
                n_results=self.emoji_config.retrieve_count
            )
            
            # 安全检查：确保结果结构完整
            documents = results.get('documents')
            distances = results.get('distances')
            metadatas = results.get('metadatas')
            
            if not documents or not documents[0]:
                logger.debug(f"🔍 未找到相关表情: {query_text}")
                return None
            
            if not distances or not distances[0] or not metadatas or not metadatas[0]:
                logger.debug(f"🔍 表情检索结果不完整")
                return None
            
            # 获取距离和路径
            distance = distances[0][0]
            metadata = metadatas[0][0]
            description = documents[0][0]
            
            if not metadata or 'path' not in metadata:
                logger.warning(f"⚠️  表情元数据缺失 path 字段")
                return None
            
            file_path = metadata['path']
            
            # 计算相似度（距离越小越相似）
            similarity = 1 - distance
            
            # 检查是否超过最低阈值（这里使用一个较低的阈值，让调用方决定是否发送）
            min_threshold = 0.2  # 最低阈值，低于此值完全不考虑
            if similarity < min_threshold:
                logger.debug(f"🔍 相似度过低 ({similarity:.2%}): {query_text}")
                return None
            
            # 检查文件是否存在
            if not Path(file_path).exists():
                logger.warning(f"⚠️  表情文件不存在: {file_path}")
                return None
            
            logger.info(f"🎯 找到表情: [{description}] 相似度: {similarity:.2%}")
            return (file_path, similarity)
            
        except Exception as e:
            logger.error(f"❌ 检索表情失败: {e}")
            return None
    
    def get_stats(self) -> dict:
        """
        获取表情库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 获取所有表情
            results = self.collection.get()
            
            total_count = len(results.get('ids', []))
            
            # 统计文件大小
            total_size = 0
            for metadata in results.get('metadatas', []):
                file_path = Path(metadata.get('path', ''))
                if file_path.exists():
                    total_size += file_path.stat().st_size
            
            return {
                "total": total_count,
                "total_size_mb": total_size / (1024 * 1024),
                "storage_path": str(self.save_dir),
                "learning_enabled": self.emoji_config.enable_learning,
                "sending_enabled": self.emoji_config.enable_sending
            }
        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {"total": 0, "error": str(e)}


# 全局单例
_emoji_service: Optional[EmojiService] = None


def get_emoji_service() -> EmojiService:
    """
    获取全局表情包服务单例
    
    注意：必须在 ConfigManager.load() 之后调用
    """
    global _emoji_service
    if _emoji_service is None:
        try:
            _emoji_service = EmojiService()
        except RuntimeError as e:
            # 配置未加载时返回友好提示
            logger.warning(f"⚠️  表情包服务延迟初始化: {e}")
            raise RuntimeError("表情包服务需要在配置加载后初始化，请确保 ConfigManager.load() 已被调用")
    return _emoji_service
