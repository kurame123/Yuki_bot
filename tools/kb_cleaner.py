"""
知识库清洗工具
使用 LLM 将不规则文本清洗成结构化的元数据
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config_manager import ConfigManager
from src.services.http_client import AsyncHTTPClient
from src.models.api_types import ChatMessage
from src.core.logger import logger


GAME_BACKGROUND = """《魔女审判》是一款推理游戏，背景设定如下：

【世界观】
- 魔女是远古种族，曾与人类共存，后被人类灭绝
- 大魔女月代雪是唯一幸存者，制造魔女因子报复人类
- 魔女因子可感染人类，女性感染者会觉醒为"预备魔女"
- 预备魔女受压力影响会魔女化，最终变成"残骸"（怪物）

【监狱系统】
- 地点：500年前魔女聚居的孤岛
- 管理者：冰上梅露露（人类）和典狱长（猫头鹰使魔）
- 魔女审判：杀人事件后强制召开，投票处刑"魔女"

【主要角色】
- 月代雪：大魔女，制造魔女因子，藏身人类社会
- 樱羽艾玛：预备魔女，月代雪的初中同学
- 二阶堂希罗：预备魔女，月代雪和艾玛的玩伴
"""


async def clean_knowledge_text(raw_text: str) -> list:
    """
    使用 LLM 清洗知识库文本
    
    Args:
        raw_text: 原始文本
        
    Returns:
        清洗后的元数据列表 [{"title": "...", "content": "..."}, ...]
    """
    ai_config = ConfigManager.get_ai_config()
    organizer = ai_config.organizer
    
    # 获取供应商配置
    provider_name = getattr(organizer, 'provider', '') or ai_config.common.default_provider
    providers = getattr(ai_config, 'providers', {})
    
    if provider_name in providers:
        provider = providers[provider_name]
        api_base = provider.api_base
        api_key = provider.api_key
        timeout = provider.timeout
    else:
        raise ValueError(f"未找到供应商配置: {provider_name}")
    
    system_prompt = f"""{GAME_BACKGROUND}

你是知识库清洗助手。将不规则的文本清洗成结构化的元数据。

【输出格式】JSON数组，每个元素包含：
- title: 简短标题（5-10字）
- content: 清晰的内容描述（30-80字）

【清洗规则】
1. 每条元数据只包含一个独立的知识点
2. 内容要客观、清晰、完整
3. 移除无关信息和重复内容
4. 保留关键设定和关系

【示例】
输入：
魔女化：预备魔女受长期的心里压力和负面影响，体内魔女因子增长，魔法增强但精神逐渐失控，产生杀人冲动。完全魔女化后变为"残骸"（非人怪物），保留记忆与魔法能力，战斗力极强。

输出：
[
  {{
    "title": "魔女化过程",
    "content": "预备魔女受长期心理压力影响，体内魔女因子增长，魔法增强但精神逐渐失控，产生杀人冲动"
  }},
  {{
    "title": "残骸形态",
    "content": "完全魔女化后变为残骸（非人怪物），保留记忆与魔法能力，战斗力极强"
  }}
]"""
    
    user_prompt = f"""请清洗以下文本：

{raw_text}

输出JSON数组："""
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt)
    ]
    
    try:
        async with AsyncHTTPClient(timeout=timeout) as client:
            response = await client.chat_completion(
                api_base=api_base,
                api_key=api_key,
                model=organizer.model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=2000,
                timeout=timeout
            )
        
        result_text = AsyncHTTPClient.parse_completion_response(response)
        
        # 解析 JSON
        import json
        import re
        
        # 提取 JSON 部分
        json_match = re.search(r'```json\s*(\[.*?\])\s*```', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(1)
        else:
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(0)
        
        data = json.loads(result_text)
        
        logger.info(f"✅ 清洗完成，生成 {len(data)} 条元数据")
        return data
    
    except Exception as e:
        logger.error(f"❌ 清洗失败: {e}")
        return []


async def process_knowledge_files():
    """处理所有知识库文件"""
    ConfigManager.load()
    
    kb_dir = Path("knowledge_docs")
    output_file = Path("data/cleaned_knowledge.json")
    
    if not kb_dir.exists():
        logger.error(f"知识库目录不存在: {kb_dir}")
        return
    
    # 检查是否存在旧文件
    if output_file.exists():
        logger.warning(f"⚠️  发现已存在的清洗数据: {output_file}")
        logger.info(f"   将覆盖旧文件")
    
    all_metadata = []
    
    # 处理所有 txt 文件
    for txt_file in kb_dir.glob("*.txt"):
        logger.info(f"📖 处理文件: {txt_file.name}")
        
        # 读取文件
        with open(txt_file, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        
        # 分段处理（每次最多2000字）
        chunks = []
        current_chunk = ""
        
        for line in raw_text.split('\n'):
            if len(current_chunk) + len(line) > 2000:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk += '\n' + line
        
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"   分成 {len(chunks)} 个片段")
        
        # 清洗每个片段
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"   处理片段 {i}/{len(chunks)}")
            metadata = await clean_knowledge_text(chunk)
            
            # 添加来源信息
            for item in metadata:
                item['source'] = txt_file.stem
            
            all_metadata.extend(metadata)
            
            # 避免请求过快
            await asyncio.sleep(2)
    
    # 保存结果
    import json
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_metadata, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 全部完成！共生成 {len(all_metadata)} 条元数据")
    logger.info(f"   保存到: {output_file}")
    
    # 显示示例
    if all_metadata:
        logger.info("\n示例元数据：")
        for item in all_metadata[:3]:
            logger.info(f"  - {item['title']}: {item['content'][:50]}...")


if __name__ == "__main__":
    asyncio.run(process_knowledge_files())
