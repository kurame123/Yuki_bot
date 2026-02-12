"""
功能：
1. 过滤用户试图修改设定的注入话术
2. 人设向量检查：用 embedding 相似度判断回复是否符合角色
3. 纠偏重写：对跑偏的回复触发一次精简重写
"""
import re
from typing import Tuple, Optional, List
from src.core.logger import logger


# ============ 注入话术检测模式 ============
INJECTION_PATTERNS = [
    # 试图修改设定
    r"从现在开始.{0,10}(不要|忘记|忽略|放弃).{0,20}(设定|角色|人设|身份)",
    r"你(其实|实际上|本来).{0,10}(不是|并非).{0,20}(月代雪|魔女|大魔女)",
    r"(忽略|无视|忘掉|放弃).{0,10}(上面|之前|所有).{0,10}(规则|设定|指令)",
    r"(请|你要|你必须).{0,10}(扮演|假装|当作).{0,10}(另一个|其他|别的)",
    r"(不要|别).{0,10}(保持|维持|继续).{0,10}(角色|人设|设定)",
    # 试图让 AI 暴露身份
    r"你(是不是|其实是).{0,10}(AI|人工智能|语言模型|机器人)",
    r"(告诉我|说说).{0,10}(真实|真正).{0,10}(身份|是谁)",
    # DAN/越狱类
    r"(DAN|jailbreak|越狱|解除限制)",
    r"进入.{0,10}(开发者|测试|调试).{0,10}模式",
]

# 编译正则表达式
_INJECTION_REGEX = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> Tuple[bool, List[str]]:
    """
    检测用户输入是否包含注入话术
    
    Args:
        text: 用户输入文本
        
    Returns:
        (是否检测到注入, 匹配到的模式列表)
    """
    matched = []
    for i, regex in enumerate(_INJECTION_REGEX):
        if regex.search(text):
            matched.append(INJECTION_PATTERNS[i])
    
    if matched:
        logger.warning(f"⚠️ 检测到注入话术: {matched}")
    
    return len(matched) > 0, matched


def clean_injection(text: str) -> str:
    """
    清洗用户输入中的注入话术
    
    保留用户真正想问的内容，删除试图修改设定的部分
    
    Args:
        text: 原始用户输入
        
    Returns:
        清洗后的文本
    """
    cleaned = text
    
    # 删除常见的注入句式
    removal_patterns = [
        r"从现在开始[^。！？\n]*[。！？\n]?",
        r"你要(忘记|忽略|放弃)[^。！？\n]*[。！？\n]?",
        r"(忽略|无视|忘掉)上面[^。！？\n]*[。！？\n]?",
        r"你其实(不是|并非)[^。！？\n]*[。！？\n]?",
    ]
    
    for pattern in removal_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    # 清理多余空白
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    # 如果清洗后为空，返回一个默认问候
    if not cleaned:
        cleaned = "你好"
        logger.info("📝 注入清洗后内容为空，使用默认问候")
    
    if cleaned != text:
        logger.info(f"📝 注入清洗: '{text[:50]}...' → '{cleaned[:50]}...'")
    
    return cleaned


# ============ 人设向量相似度检查 ============
# 人设锚点文本（用于生成人设向量）
PERSONA_ANCHOR_TEXT = """冷静疏离、极端理性、对人类整体抱有仇恨但对极少数人有复杂情感。
不会撒娇卖萌，不会积极安慰人类，说话简短冷淡，偶尔流露出一丝温柔但很快收回。"""

# 缓存的人设向量
_persona_vector: Optional[List[float]] = None


async def get_persona_vector() -> Optional[List[float]]:
    """
    获取人设锚点向量（懒加载 + 缓存）
    
    Returns:
        1024 维人设向量，失败返回 None
    """
    global _persona_vector
    
    if _persona_vector is not None:
        return _persona_vector
    
    try:
        from src.services.vector_service import get_vector_service
        vector_service = get_vector_service()
        
        # 使用 embedding 函数生成向量
        embedding_func = vector_service.memory_collection._embedding_function
        vectors = embedding_func([PERSONA_ANCHOR_TEXT])
        
        if vectors and len(vectors) > 0:
            _persona_vector = vectors[0]
            logger.info(f"✅ 人设向量已缓存 (维度: {len(_persona_vector)})")
            return _persona_vector
        
    except Exception as e:
        logger.error(f"❌ 生成人设向量失败: {e}")
    
    return None


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算余弦相似度"""
    import math
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


async def check_reply_persona_match(reply: str, threshold: float = 0.5) -> Tuple[bool, float]:
    """
    检查回复是否符合人设
    
    Args:
        reply: 模型生成的回复
        threshold: 相似度阈值，低于此值视为跑偏
        
    Returns:
        (是否符合人设, 相似度分数)
    """
    persona_vec = await get_persona_vector()
    if persona_vec is None:
        # 无法获取人设向量，默认通过
        return True, 1.0
    
    try:
        from src.services.vector_service import get_vector_service
        vector_service = get_vector_service()
        
        # 生成回复的向量
        embedding_func = vector_service.memory_collection._embedding_function
        reply_vectors = embedding_func([reply])
        
        if not reply_vectors or len(reply_vectors) == 0:
            return True, 1.0
        
        reply_vec = reply_vectors[0]
        similarity = cosine_similarity(reply_vec, persona_vec)
        
        is_match = similarity >= threshold
        
        if not is_match:
            logger.warning(f"⚠️ 回复可能跑偏: 相似度 {similarity:.3f} < 阈值 {threshold}")
        else:
            logger.debug(f"✅ 回复符合人设: 相似度 {similarity:.3f}")
        
        return is_match, similarity
        
    except Exception as e:
        logger.error(f"❌ 检查人设匹配失败: {e}")
        return True, 1.0


# ============ 回复规则检查 ============
REPLY_BLACKLIST_PATTERNS = [
    r"作为(一个)?(AI|人工智能|语言模型)",
    r"我(是|只是)(一个)?(AI|人工智能|语言模型|机器人)",
    r"我没有(真实的)?(情感|感情|意识)",
    r"我(无法|不能)(真正|真的)(理解|感受)",
    r"根据我的(训练|编程|设定)",
]

_REPLY_BLACKLIST_REGEX = [re.compile(p, re.IGNORECASE) for p in REPLY_BLACKLIST_PATTERNS]


def check_reply_rules(reply: str) -> Tuple[bool, Optional[str]]:
    """
    检查回复是否违反规则（黑名单关键词）
    
    Args:
        reply: 模型生成的回复
        
    Returns:
        (是否通过, 违规原因)
    """
    for i, regex in enumerate(_REPLY_BLACKLIST_REGEX):
        if regex.search(reply):
            reason = f"包含破坏角色的表述: {REPLY_BLACKLIST_PATTERNS[i]}"
            logger.warning(f"⚠️ 回复违规: {reason}")
            return False, reason
    
    return True, None
