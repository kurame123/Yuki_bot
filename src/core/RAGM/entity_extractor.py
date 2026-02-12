"""
实体和关系提取器
使用 LLM 从对话中提取关键实体和关系
"""
import asyncio
from typing import List, Dict, Any, Tuple
from src.core.logger import logger
from src.core.config_manager import ConfigManager
from src.services.http_client import AsyncHTTPClient
from src.models.api_types import ChatMessage


class EntityExtractor:
    """实体和关系提取器"""
    
    def __init__(self):
        self.config = ConfigManager.get_ai_config()
        logger.info("✅ 实体提取器初始化")
    
    async def extract_from_dialogue(
        self, 
        user_message: str, 
        bot_reply: str,
        user_name: str = "用户"
    ) -> Dict[str, Any]:
        """
        从对话中提取实体和关系(增强版: 支持时间和指代消歧)
        
        Returns:
            {
                "entities": [{"name": "实体名", "type": "类型", "alias": "别名/指代"}, ...],
                "relations": [{"source": "A", "target": "B", "relation": "关系", "time_ref": "时间指代"}, ...],
                "time_context": "时间上下文(如: 昨天、上次、最近)"
            }
        """
        # 构建提取提示词(增强版)
        system_prompt = f"""你是知识图谱构建助手。从对话中提取关键实体、关系和时间信息。

【输出格式】JSON格式，包含三个字段：
1. entities: 实体列表，每个实体包含：
   - name: 实体名（具体名称，如"艾玛"）
   - type: 类型（人物/地点/事件/物品/情感/其他）
   - alias: 别名或指代（如"她"、"那个人"，没有则为空）
   
2. relations: 关系列表，每个关系包含：
   - source: 源实体（具体名称）
   - target: 目标实体（具体名称）
   - relation: 关系描述（动词短语，如"喜欢"、"去过"、"讨厌"）
   - time_ref: 时间指代（如"昨天"、"上次"、"最近"、"现在"，没有则为空）
   
3. time_context: 对话中的时间上下文（如"昨天"、"上次"、"刚才"，没有则为空）

【提取规则】
- 只提取重要的实体（人名、地名、事件、物品等）
- 关系要简洁明确（如：喜欢、讨厌、去过、拥有、提到等）
- 月代雪是 Bot，{user_name} 是用户
- **重点**：如果对话中有"她"、"他"、"那个"等指代词，尝试推断具体指代谁，填入 alias 字段
- **重点**：如果对话中有时间词（昨天、上次、最近、刚才等），提取到 time_ref 和 time_context
- 如果没有明显实体或关系，返回空列表

【示例1 - 基础提取】
输入：
用户：我昨天去了东京塔
Bot：东京塔的夜景很美

输出：
{{
  "entities": [
    {{"name": "{user_name}", "type": "人物", "alias": ""}},
    {{"name": "东京塔", "type": "地点", "alias": ""}}
  ],
  "relations": [
    {{"source": "{user_name}", "target": "东京塔", "relation": "去过", "time_ref": "昨天"}}
  ],
  "time_context": "昨天"
}}

【示例2 - 指代消歧】
输入：
用户：你怎么知道她不需要
Bot：艾玛她...早就不在意了

输出：
{{
  "entities": [
    {{"name": "艾玛", "type": "人物", "alias": "她"}},
    {{"name": "月代雪", "type": "人物", "alias": ""}}
  ],
  "relations": [
    {{"source": "月代雪", "target": "艾玛", "relation": "提到", "time_ref": ""}},
    {{"source": "艾玛", "target": "道歉", "relation": "不在意", "time_ref": ""}}
  ],
  "time_context": ""
}}

【示例3 - 时间映射】
输入：
用户：上次那件事你还记得吗
Bot：记得，你说的是关于焙茶的事吧

输出：
{{
  "entities": [
    {{"name": "焙茶", "type": "物品", "alias": "那件事"}},
    {{"name": "{user_name}", "type": "人物", "alias": ""}}
  ],
  "relations": [
    {{"source": "{user_name}", "target": "焙茶", "relation": "提到", "time_ref": "上次"}}
  ],
  "time_context": "上次"
}}"""
        
        user_prompt = f"""【对话内容】
{user_name}：{user_message}
月代雪：{bot_reply}

请提取实体和关系（JSON格式）："""
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt)
        ]
        
        try:
            # 使用 Organizer 模型（更便宜）
            organizer = self.config.organizer
            provider_name = getattr(organizer, 'provider', '') or self.config.common.default_provider
            providers = getattr(self.config, 'providers', {})
            
            if provider_name in providers:
                provider = providers[provider_name]
                api_base = provider.api_base
                api_key = provider.api_key
                timeout = provider.timeout
            else:
                raise ValueError(f"未找到供应商配置: {provider_name}")
            
            async with AsyncHTTPClient(timeout=timeout) as client:
                response = await client.chat_completion(
                    api_base=api_base,
                    api_key=api_key,
                    model=organizer.model_name,
                    messages=messages,
                    temperature=0.4,  # 低温度保证稳定输出
                    max_tokens=500,
                    timeout=timeout
                )
            
            result_text = AsyncHTTPClient.parse_completion_response(response)
            
            # 记录 LLM 原始输出
            logger.info(f"🤖 [图谱提取] LLM 原始输出:\n{result_text}")
            
            # 解析 JSON
            import json
            import re
            
            # 提取 JSON 部分（可能被包裹在 ```json ``` 中）
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(1)
            else:
                # 尝试直接提取 JSON 对象
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group(0)
            
            data = json.loads(result_text)
            
            # 验证格式
            if "entities" not in data:
                data["entities"] = []
            if "relations" not in data:
                data["relations"] = []
            if "time_context" not in data:
                data["time_context"] = ""
            
            # 详细日志
            logger.info(f"🔍 [图谱提取] 解析成功:")
            logger.info(f"   时间上下文: {data.get('time_context', '无')}")
            logger.info(f"   实体数: {len(data['entities'])}")
            if data['entities']:
                for entity in data['entities']:
                    alias_info = f" (别名: {entity.get('alias')})" if entity.get('alias') else ""
                    logger.info(f"     - {entity.get('name', '?')} ({entity.get('type', '?')}){alias_info}")
            
            logger.info(f"   关系数: {len(data['relations'])}")
            if data['relations']:
                for relation in data['relations']:
                    time_info = f" [{relation.get('time_ref')}]" if relation.get('time_ref') else ""
                    logger.info(f"     - {relation.get('source', '?')} → {relation.get('relation', '?')} → {relation.get('target', '?')}{time_info}")
            
            return data
        
        except Exception as e:
            logger.warning(f"⚠️ 实体提取失败: {e}")
            logger.debug(f"   原始输出: {result_text if 'result_text' in locals() else 'N/A'}")
            return {"entities": [], "relations": []}


# 全局单例
_entity_extractor = None


def get_entity_extractor():
    """获取全局实体提取器单例"""
    global _entity_extractor
    if _entity_extractor is None:
        _entity_extractor = EntityExtractor()
    return _entity_extractor
