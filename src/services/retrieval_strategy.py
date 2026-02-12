"""
检索策略模块 - 月代雪知识库多层次检索优化

实现功能：
1. 多层次检索架构（精确匹配 + 语义相似度 + 上下文相关性）
2. 角色专属关键词权重
3. 场景感知检索
4. 检索结果后处理与重排序
5. 动态权重调整
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re
import time

from src.core.logger import logger


class SceneType(Enum):
    """对话场景类型"""
    IDENTITY = "identity"       # 身份询问
    EMOTION = "emotion"         # 情感表达
    DAILY = "daily"             # 日常交流
    DEEP = "deep"               # 深度对话
    GREETING = "greeting"       # 问候寒暄
    UNKNOWN = "unknown"         # 未知场景


@dataclass
class RetrievalResult:
    """检索结果数据类"""
    content: str
    source: str
    original_score: float
    final_score: float
    match_type: str  # "keyword", "semantic", "hybrid"
    matched_keywords: List[str]


class RetrievalStrategy:
    """
    多层次检索策略
    
    检索流程：
    1. 场景识别 → 确定检索重点
    2. 关键词匹配 → 精确匹配加分
    3. 语义检索 → 向量相似度
    4. 结果重排序 → 综合评分
    5. 后处理过滤 → 质量保证
    """
    
    # ============ 角色专属关键词权重配置 ============
    KEYWORD_WEIGHTS = {
        # 核心角色关键词（最高优先级）
        "角色核心": {
            "月代雪": 10.0,
            "小雪": 8.0,
            "月雪": 8.0,
            "月代": 7.0,
        },
        # 身份相关
        "身份背景": {
            "大魔女": 8.0,
            "魔女因子": 7.0,
            "魔女种族": 8.0,
            "最后幸存者": 9.0,
            "魔女审判": 7.0,
            "灭世计划": 6.0,
            "复仇": 5.0,
        },
        # 角色关系
        "角色关系": {
            "艾玛": 4.0,
            "希罗": 4.0,
            "樱羽艾玛": 6.0,
            "二阶堂希罗": 6.0,
        },
        # 性格特征
        "性格特征": {
            "孤独": 5.0,
            "冷漠": 4.0,
            "理性": 4.0,
            "矛盾": 5.0,
            "伪装": 5.0,
            "观察": 4.0,
        },
    }
    
    # ============ 同义词扩展映射 ============
    SYNONYM_MAP = {
        "月代雪": ["月雪", "雪", "小雪", "月代"],
        "魔女": ["大魔女", "魔女因子", "魔女种族", "最后幸存者"],
        "朋友": ["同伴", "伙伴", "友人"],
        "孤独": ["寂寞", "独自", "一个人"],
        "复仇": ["报仇", "仇恨", "灭世"],
    }
    
    # ============ 负向过滤关键词 ============
    NEGATIVE_KEYWORDS = {
        # 其他角色特征（避免混淆）
        "其他角色": ["侦探", "明星", "艺人", "演员", "dayo", "慵懒", "尾音"],
        # 无关主题
        "无关主题": ["推理", "表演", "演艺", "犯罪调查"],
    }
    
    # ============ 场景识别关键词 ============
    SCENE_KEYWORDS = {
        SceneType.IDENTITY: ["你是谁", "真实身份", "大魔女", "魔女", "身份", "你叫什么", "介绍一下自己"],
        SceneType.EMOTION: ["喜欢", "爱", "讨厌", "感觉", "心情", "开心", "难过", "孤独", "寂寞"],
        SceneType.DAILY: ["今天", "早上", "晚上", "吃", "做什么", "在干嘛", "天气"],
        SceneType.DEEP: ["人生", "意义", "为什么", "存在", "命运", "未来", "过去"],
        SceneType.GREETING: ["你好", "早安", "晚安", "嗨", "在吗", "hello", "hi"],
    }
    
    # ============ 场景对应的检索重点 ============
    SCENE_RETRIEVAL_FOCUS = {
        SceneType.IDENTITY: ["身份背景", "角色核心"],
        SceneType.EMOTION: ["性格特征", "角色关系"],
        SceneType.DAILY: ["性格特征"],
        SceneType.DEEP: ["身份背景", "性格特征"],
        SceneType.GREETING: ["性格特征"],
        SceneType.UNKNOWN: ["角色核心", "性格特征"],
    }
    
    def __init__(self, similarity_threshold: float = 0.5):
        """
        初始化检索策略
        
        Args:
            similarity_threshold: 语义相似度阈值（优化后提升到0.5）
        """
        self.similarity_threshold = similarity_threshold
        self.keyword_weight_ratio = 0.4  # 关键词匹配权重
        self.semantic_weight_ratio = 0.6  # 语义相似度权重
        
        # 构建扁平化的关键词权重表
        self._flat_keyword_weights = {}
        for category, keywords in self.KEYWORD_WEIGHTS.items():
            for kw, weight in keywords.items():
                self._flat_keyword_weights[kw] = (weight, category)
        
        logger.info(f"🎯 检索策略初始化完成")
        logger.info(f"   - 相似度阈值: {self.similarity_threshold}")
        logger.info(f"   - 关键词权重比: {self.keyword_weight_ratio}")
        logger.info(f"   - 语义权重比: {self.semantic_weight_ratio}")

    def identify_scene(self, query: str, conversation_history: Optional[List[str]] = None) -> SceneType:
        """
        识别对话场景
        
        Args:
            query: 用户查询
            conversation_history: 对话历史（可选）
            
        Returns:
            场景类型
        """
        query_lower = query.lower()
        
        # 按优先级检查场景关键词
        scene_scores = {}
        for scene_type, keywords in self.SCENE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                scene_scores[scene_type] = score
        
        if scene_scores:
            # 返回得分最高的场景
            best_scene = max(scene_scores, key=scene_scores.get)
            logger.debug(f"🎭 场景识别: {query[:20]}... → {best_scene.value}")
            return best_scene
        
        return SceneType.UNKNOWN
    
    def extract_keywords(self, text: str) -> List[Tuple[str, float, str]]:
        """
        从文本中提取关键词及其权重
        
        Args:
            text: 输入文本
            
        Returns:
            [(关键词, 权重, 类别), ...]
        """
        found_keywords = []
        
        for keyword, (weight, category) in self._flat_keyword_weights.items():
            if keyword in text:
                found_keywords.append((keyword, weight, category))
        
        # 按权重降序排列
        found_keywords.sort(key=lambda x: x[1], reverse=True)
        return found_keywords
    
    def expand_query(self, query: str) -> List[str]:
        """
        查询扩展 - 添加同义词
        
        Args:
            query: 原始查询
            
        Returns:
            扩展后的查询词列表
        """
        expanded = [query]
        
        for key, synonyms in self.SYNONYM_MAP.items():
            if key in query:
                expanded.extend(synonyms)
        
        return list(set(expanded))
    
    def calculate_keyword_score(self, content: str, query: str, scene: SceneType) -> Tuple[float, List[str]]:
        """
        计算关键词匹配得分
        
        Args:
            content: 检索到的内容
            query: 用户查询
            scene: 对话场景
            
        Returns:
            (得分, 匹配的关键词列表)
        """
        score = 0.0
        matched_keywords = []
        
        # 1. 检查内容中的关键词
        content_keywords = self.extract_keywords(content)
        
        # 2. 根据场景调整权重
        focus_categories = self.SCENE_RETRIEVAL_FOCUS.get(scene, ["角色核心"])
        
        for keyword, weight, category in content_keywords:
            # 场景相关的类别加成
            if category in focus_categories:
                weight *= 1.3
            
            # 如果查询中也包含该关键词，额外加成
            if keyword in query:
                weight *= 1.5
            
            score += weight
            matched_keywords.append(keyword)
        
        # 3. 角色名直接匹配的额外加分
        if "月代雪" in content:
            score += 3.0
            if "月代雪" not in matched_keywords:
                matched_keywords.append("月代雪")
        
        # 归一化到 0-1 范围（假设最大可能得分约为 30）
        normalized_score = min(score / 30.0, 1.0)
        
        return normalized_score, matched_keywords
    
    def check_negative_filter(self, content: str) -> bool:
        """
        检查是否应该过滤该内容（负向过滤）
        
        Args:
            content: 检索内容
            
        Returns:
            True = 应该过滤掉, False = 保留
        """
        for category, keywords in self.NEGATIVE_KEYWORDS.items():
            for kw in keywords:
                if kw in content and "月代雪" not in content:
                    # 如果包含负向关键词且不包含月代雪，过滤掉
                    logger.debug(f"🚫 负向过滤: 包含 '{kw}' (类别: {category})")
                    return True
        return False
    
    def check_content_completeness(self, content: str) -> float:
        """
        检查内容完整性
        
        Args:
            content: 检索内容
            
        Returns:
            完整性得分 (0-1)
        """
        score = 1.0
        
        # 检查是否被截断（以不完整的标点结尾）
        if content.endswith(('，', '、', '：', '的', '是', '在', '和')):
            score -= 0.2
        
        # 检查长度（太短可能是碎片）
        if len(content) < 20:
            score -= 0.3
        elif len(content) < 50:
            score -= 0.1
        
        # 检查是否包含完整句子（有句号、问号、感叹号）
        if not any(p in content for p in ['。', '！', '？', '!', '?', '.']):
            score -= 0.1
        
        return max(score, 0.0)
    
    def rerank_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        scene: SceneType
    ) -> List[RetrievalResult]:
        """
        重排序检索结果
        
        Args:
            results: 原始检索结果 [{"content": str, "source": str, "similarity": float}, ...]
            query: 用户查询
            scene: 对话场景
            
        Returns:
            重排序后的结果列表
        """
        reranked = []
        
        for result in results:
            content = result.get("content", "")
            source = result.get("source", "Unknown")
            original_score = result.get("similarity", 0.0)
            
            # 1. 负向过滤
            if self.check_negative_filter(content):
                continue
            
            # 2. 计算关键词得分
            keyword_score, matched_keywords = self.calculate_keyword_score(content, query, scene)
            
            # 3. 计算内容完整性
            completeness = self.check_content_completeness(content)
            
            # 4. 综合评分
            # 最终得分 = 关键词得分 * 0.4 + 语义得分 * 0.6 + 完整性加成
            final_score = (
                keyword_score * self.keyword_weight_ratio +
                original_score * self.semantic_weight_ratio +
                completeness * 0.1  # 完整性小幅加成
            )
            
            # 确定匹配类型
            if keyword_score > 0.3 and original_score > 0.5:
                match_type = "hybrid"
            elif keyword_score > 0.3:
                match_type = "keyword"
            else:
                match_type = "semantic"
            
            reranked.append(RetrievalResult(
                content=content,
                source=source,
                original_score=original_score,
                final_score=final_score,
                match_type=match_type,
                matched_keywords=matched_keywords
            ))
        
        # 按最终得分降序排列
        reranked.sort(key=lambda x: x.final_score, reverse=True)
        
        return reranked
    
    def filter_by_threshold(
        self,
        results: List[RetrievalResult],
        min_score: Optional[float] = None
    ) -> List[RetrievalResult]:
        """
        根据阈值过滤结果
        
        Args:
            results: 重排序后的结果
            min_score: 最低分数阈值（默认使用配置值）
            
        Returns:
            过滤后的结果
        """
        if min_score is None:
            min_score = self.similarity_threshold
        
        filtered = [r for r in results if r.final_score >= min_score]
        
        logger.debug(f"🔍 阈值过滤: {len(results)} → {len(filtered)} (阈值: {min_score})")
        
        return filtered
    
    def format_results(self, results: List[RetrievalResult], max_results: int = 3) -> str:
        """
        格式化检索结果为字符串
        
        Args:
            results: 检索结果列表
            max_results: 最大返回数量
            
        Returns:
            格式化的字符串
        """
        if not results:
            return ""
        
        # 取前 N 条
        top_results = results[:max_results]
        
        lines = []
        for i, result in enumerate(top_results, 1):
            # 移除文件扩展名作为标题
            title = result.source.rsplit('.', 1)[0] if '.' in result.source else result.source
            
            # 只输出标题和内容，省略调试信息
            lines.append(f"{i}. {title}：{result.content}")
        
        return "\n".join(lines)


# 全局单例
_retrieval_strategy: Optional[RetrievalStrategy] = None


def get_retrieval_strategy() -> RetrievalStrategy:
    """获取全局检索策略单例"""
    global _retrieval_strategy
    if _retrieval_strategy is None:
        _retrieval_strategy = RetrievalStrategy()
    return _retrieval_strategy


def reset_retrieval_strategy() -> None:
    """重置检索策略单例（用于热重载配置）"""
    global _retrieval_strategy
    _retrieval_strategy = None
    logger.info("🔄 检索策略已重置，下次使用时将重新加载配置")
