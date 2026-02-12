"""
AI 驱动的知识图谱清理器

使用 LLM 智能识别：
1. 重复实体（语义相似）
2. 无用节点（无意义或错误提取的实体）
3. 应该合并的实体
"""
import json
from typing import List, Dict, Any, Tuple, Optional
from src.core.logger import logger
from src.core.RAGM.graph_storage import GraphStorage


class AIGraphCleaner:
    """AI 驱动的图谱清理器"""
    
    def __init__(self, graph_storage: GraphStorage):
        self.storage = graph_storage
        logger.info("✅ AI 图谱清理器初始化")
    
    async def identify_duplicate_entities(
        self,
        user_id: str,
        entities: List[Dict[str, Any]]
    ) -> List[Tuple[str, List[str]]]:
        """
        使用 AI 识别重复实体
        
        Args:
            user_id: 用户 ID
            entities: 实体列表 [{"entity": "小明", "type": "人物", "aliases": [...]}, ...]
            
        Returns:
            [(主实体, [重复实体1, 重复实体2, ...]), ...]
        """
        if len(entities) < 2:
            return []
        
        try:
            from src.core.config_manager import ConfigManager
            from src.services.http_client import AsyncHTTPClient
            from src.models.api_types import ChatMessage
            
            ai_config = ConfigManager.get_ai_config()
            organizer = ai_config.organizer
            
            # 构建实体列表文本
            entity_list = []
            for i, e in enumerate(entities[:50], 1):  # 最多50个实体
                aliases = e.get('aliases', [])
                alias_str = f" (别名: {', '.join(aliases)})" if aliases else ""
                entity_list.append(f"{i}. {e['entity']} ({e.get('type', '未知')}){alias_str}")
            
            entity_text = "\n".join(entity_list)
            
            # 构建提示词
            system_prompt = """你是知识图谱清理专家。分析实体列表，识别重复或相似的实体。

【判断标准】
1. 语义相同：如"小明"和"小明同学"
2. 指代相同：如"她"和"小红"（如果别名中有关联）
3. 简写/全称：如"北京"和"北京市"
4. 错别字：如"小明"和"小名"

【输出格式】
只输出 JSON 数组，每组重复实体一个对象：
```json
[
  {"main": "小明", "duplicates": ["小明同学", "那个小明"]},
  {"main": "北京", "duplicates": ["北京市"]}
]
```

如果没有重复实体，输出空数组：[]

【注意】
- 只输出 JSON，不要其他内容
- main 是保留的主实体
- duplicates 是要合并到 main 的重复实体
- 不确定的不要输出"""
            
            user_prompt = f"""用户 {user_id} 的实体列表：

{entity_text}

请识别重复实体："""
            
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt)
            ]
            
            # 获取供应商配置
            provider_name = getattr(organizer, 'provider', '') or ai_config.common.default_provider
            providers = getattr(ai_config, 'providers', {})
            
            if provider_name not in providers:
                logger.warning(f"⚠️ AI 清理: 未找到供应商 {provider_name}")
                return []
            
            provider = providers[provider_name]
            
            async with AsyncHTTPClient(timeout=provider.timeout) as client:
                response = await client.chat_completion(
                    api_base=provider.api_base,
                    api_key=provider.api_key,
                    model=organizer.model_name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000,
                    timeout=provider.timeout
                )
            
            result = AsyncHTTPClient.parse_completion_response(response)
            
            if not result:
                return []
            
            # 解析 JSON
            # 提取 JSON 部分（可能包含 ```json ... ```）
            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].split("```")[0].strip()
            
            duplicates_data = json.loads(result)
            
            if not isinstance(duplicates_data, list):
                logger.warning(f"⚠️ AI 清理: 返回格式错误")
                return []
            
            # 转换为元组列表
            duplicates = []
            for item in duplicates_data:
                main = item.get("main", "")
                dups = item.get("duplicates", [])
                if main and dups:
                    duplicates.append((main, dups))
            
            logger.info(f"🤖 [AI 清理] 识别到 {len(duplicates)} 组重复实体")
            for main, dups in duplicates:
                logger.info(f"   - {main} ← {', '.join(dups)}")
            
            return duplicates
        
        except Exception as e:
            logger.warning(f"⚠️ AI 识别重复实体失败: {e}")
            return []
    
    async def identify_useless_entities(
        self,
        user_id: str,
        entities: List[Dict[str, Any]]
    ) -> List[str]:
        """
        使用 AI 识别无用实体
        
        Args:
            user_id: 用户 ID
            entities: 实体列表
            
        Returns:
            无用实体名称列表
        """
        if not entities:
            return []
        
        try:
            from src.core.config_manager import ConfigManager
            from src.services.http_client import AsyncHTTPClient
            from src.models.api_types import ChatMessage
            
            ai_config = ConfigManager.get_ai_config()
            organizer = ai_config.organizer
            
            # 构建实体列表文本（包含关系数量信息）
            entity_list = []
            for i, e in enumerate(entities[:50], 1):
                # 获取实体的关系数量
                import sqlite3
                conn = sqlite3.connect(str(self.storage.db_path))
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) FROM edges
                    WHERE user_id = ? AND (source_entity = ? OR target_entity = ?)
                """, (user_id, e['entity'], e['entity']))
                
                edge_count = cursor.fetchone()[0]
                conn.close()
                
                edge_info = f" [{edge_count}条关系]" if edge_count > 0 else " [孤立]"
                entity_list.append(f"{i}. {e['entity']} ({e.get('type', '未知')}){edge_info}")
            
            entity_text = "\n".join(entity_list)
            
            # 构建提示词
            system_prompt = """你是知识图谱清理专家。分析实体列表，识别无用、低价值或孤立的实体。

【无用实体标准】
1. **孤立实体**（0条关系）：完全没有关系的实体
2. **无意义词**：如"这个"、"那个"、"东西"、"事情"
3. **通用动词**：如"做"、"说"、"去"、"看"
4. **单字实体**：如"的"、"了"、"吗"（除非是有意义的名字）
5. **错误提取**：如"不知道"、"没有"、"可能"
6. **过于泛化**：如"问题"、"情况"、"方面"
7. **低价值实体**：虽有关系但无实际意义的实体

【保留实体】
1. 具体人名、地名、物品名
2. 有明确含义的实体
3. 专有名词
4. 有多条关系的重要实体

【输出格式】
只输出 JSON 数组，包含无用实体的名称：
```json
["这个", "那个", "东西", "不知道"]
```

如果没有无用实体，输出空数组：[]

【注意】
- 只输出 JSON，不要其他内容
- 优先删除孤立实体（0条关系）
- 宁可保守，不确定的不要删除
- 有多条关系的实体要谨慎判断"""
            
            user_prompt = f"""用户 {user_id} 的实体列表：

{entity_text}

请识别无用、低价值或孤立的实体："""
            
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt)
            ]
            
            # 获取供应商配置
            provider_name = getattr(organizer, 'provider', '') or ai_config.common.default_provider
            providers = getattr(ai_config, 'providers', {})
            
            if provider_name not in providers:
                logger.warning(f"⚠️ AI 清理: 未找到供应商 {provider_name}")
                return []
            
            provider = providers[provider_name]
            
            async with AsyncHTTPClient(timeout=provider.timeout) as client:
                response = await client.chat_completion(
                    api_base=provider.api_base,
                    api_key=provider.api_key,
                    model=organizer.model_name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=500,
                    timeout=provider.timeout
                )
            
            result = AsyncHTTPClient.parse_completion_response(response)
            
            if not result:
                return []
            
            # 解析 JSON
            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].split("```")[0].strip()
            
            useless_entities = json.loads(result)
            
            if not isinstance(useless_entities, list):
                logger.warning(f"⚠️ AI 清理: 返回格式错误")
                return []
            
            # 分类统计
            orphan_count = 0
            low_value_count = 0
            
            for entity in useless_entities:
                # 检查是否是孤立实体
                import sqlite3
                conn = sqlite3.connect(str(self.storage.db_path))
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) FROM edges
                    WHERE user_id = ? AND (source_entity = ? OR target_entity = ?)
                """, (user_id, entity, entity))
                
                edge_count = cursor.fetchone()[0]
                conn.close()
                
                if edge_count == 0:
                    orphan_count += 1
                else:
                    low_value_count += 1
            
            logger.info(f"🤖 [AI 清理] 识别到 {len(useless_entities)} 个无用实体")
            logger.info(f"   - 孤立实体: {orphan_count} 个")
            logger.info(f"   - 低价值实体: {low_value_count} 个")
            if useless_entities:
                logger.info(f"   - 列表: {', '.join(useless_entities)}")
            
            return useless_entities
        
        except Exception as e:
            logger.warning(f"⚠️ AI 识别无用实体失败: {e}")
            return []
    
    async def ai_cleanup_user(self, user_id: str) -> Dict[str, int]:
        """
        使用 AI 清理指定用户的图谱
        
        Args:
            user_id: 用户 ID
            
        Returns:
            {"merged": 合并数, "deleted": 删除数}
        """
        logger.info(f"🤖 [AI 清理] 开始清理用户 {user_id}")
        
        # 1. 获取用户的所有实体
        entities = self.storage.search_entities(user_id, "", limit=100)
        
        if not entities:
            logger.info(f"   用户 {user_id} 没有实体")
            return {"merged": 0, "deleted": 0}
        
        logger.info(f"   用户 {user_id} 有 {len(entities)} 个实体")
        
        # 2. AI 识别重复实体
        duplicates = await self.identify_duplicate_entities(user_id, entities)
        
        # 3. AI 识别无用实体
        useless = await self.identify_useless_entities(user_id, entities)
        
        # 4. 执行清理
        merged_count = 0
        deleted_count = 0
        
        # 合并重复实体
        if duplicates:
            import sqlite3
            conn = sqlite3.connect(str(self.storage.db_path))
            cursor = conn.cursor()
            
            try:
                for main_entity, dup_entities in duplicates:
                    # 验证实体存在
                    cursor.execute("""
                        SELECT entity, entity_type, properties
                        FROM nodes
                        WHERE user_id = ? AND entity = ?
                    """, (user_id, main_entity))
                    
                    main_row = cursor.fetchone()
                    if not main_row:
                        logger.warning(f"   ⚠️ 主实体 '{main_entity}' 不存在，跳过")
                        continue
                    
                    # 收集重复实体信息
                    dup_list = []
                    for dup_entity in dup_entities:
                        cursor.execute("""
                            SELECT entity, entity_type, properties
                            FROM nodes
                            WHERE user_id = ? AND entity = ?
                        """, (user_id, dup_entity))
                        
                        dup_row = cursor.fetchone()
                        if dup_row:
                            entity, etype, props = dup_row
                            props_dict = json.loads(props) if props else {}
                            dup_list.append((entity, etype, props_dict))
                    
                    if dup_list:
                        # 执行合并
                        self.storage._merge_entities(cursor, user_id, main_entity, dup_list)
                        merged_count += len(dup_list)
                        logger.info(f"   ✅ 合并: {main_entity} ← {', '.join([d[0] for d in dup_list])}")
                
                conn.commit()
            finally:
                conn.close()
        
        # 删除无用实体
        if useless:
            import sqlite3
            conn = sqlite3.connect(str(self.storage.db_path))
            cursor = conn.cursor()
            
            try:
                for entity in useless:
                    # 删除相关的边
                    cursor.execute("""
                        DELETE FROM edges
                        WHERE user_id = ? AND (source_entity = ? OR target_entity = ?)
                    """, (user_id, entity, entity))
                    
                    # 删除节点
                    cursor.execute("""
                        DELETE FROM nodes
                        WHERE user_id = ? AND entity = ?
                    """, (user_id, entity))
                    
                    if cursor.rowcount > 0:
                        deleted_count += 1
                        logger.info(f"   🗑️ 删除无用实体: {entity}")
                
                conn.commit()
            finally:
                conn.close()
        
        logger.info(f"🤖 [AI 清理] 用户 {user_id} 完成: 合并 {merged_count} 个, 删除 {deleted_count} 个")
        
        return {"merged": merged_count, "deleted": deleted_count}
    
    async def ai_cleanup_all_users(self, limit: int = 10) -> Dict[str, Any]:
        """
        使用 AI 清理所有用户的图谱
        
        Args:
            limit: 最多清理多少个用户（避免 API 调用过多）
            
        Returns:
            {"total_merged": 总合并数, "total_deleted": 总删除数, "users_processed": 处理的用户数}
        """
        logger.info(f"🤖 [AI 清理] 开始清理所有用户（最多 {limit} 个）")
        
        # 获取用户列表（按节点数排序）
        users = self.storage.get_users()
        
        total_merged = 0
        total_deleted = 0
        users_processed = 0
        
        for user_info in users[:limit]:
            user_id = user_info["user_id"]
            
            result = await self.ai_cleanup_user(user_id)
            
            total_merged += result["merged"]
            total_deleted += result["deleted"]
            users_processed += 1
        
        logger.info(f"🤖 [AI 清理] 全局完成: 处理 {users_processed} 个用户, 合并 {total_merged} 个, 删除 {total_deleted} 个")
        
        return {
            "total_merged": total_merged,
            "total_deleted": total_deleted,
            "users_processed": users_processed
        }


# 全局单例
_ai_graph_cleaner: Optional[AIGraphCleaner] = None


def get_ai_graph_cleaner(graph_storage: GraphStorage = None) -> AIGraphCleaner:
    """获取全局 AI 图谱清理器单例"""
    global _ai_graph_cleaner
    if _ai_graph_cleaner is None:
        if graph_storage is None:
            from src.core.RAGM.graph_storage import get_graph_storage
            graph_storage = get_graph_storage()
        _ai_graph_cleaner = AIGraphCleaner(graph_storage)
    return _ai_graph_cleaner
