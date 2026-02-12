"""
配置文件的 Pydantic 数据模型定义
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ============ 存储和向量数据库配置 ============
class StorageConfig(BaseModel):
    """长期记忆存储配置"""
    vector_db_path: str = Field(default="./data/chroma_db", description="向量数据库路径")
    retrieve_count: int = Field(default=10, description="每次检索的记忆条数")
    similarity_threshold: float = Field(default=0.4, description="相似度阈值")
    min_memory_length: int = Field(default=5, description="最短记忆长度")
    max_memory_per_user: int = Field(default=500, description="单用户最多记忆条数")
    enable_vector_memory: bool = Field(default=True, description="是否启用向量记忆")
    
    class Config:
        extra = "allow"


class EmbeddingConfig(BaseModel):
    """嵌入模型配置"""
    model_name: str = Field(default="BAAI/bge-m3", description="嵌入模型名称")
    batch_size: int = Field(default=1, description="批处理大小")
    vector_dim: int = Field(default=1024, description="向量维度")
    
    class Config:
        extra = "allow"


# ============ Bot 配置模型 ============
class ReplyStrategyConfig(BaseModel):
    """回复策略配置（消息拆分和拟人化）"""
    enable_split: bool = Field(default=True, description="是否启用长消息拆分")
    split_threshold: int = Field(default=50, description="超过多少字才开始尝试拆分")
    min_segment_length: int = Field(default=5, description="每一段最小长度")
    typing_speed: float = Field(default=0.15, description="模拟打字速度（秒/字符）")
    max_delay: float = Field(default=5.0, description="最大延迟上限（秒）")
    
    class Config:
        extra = "allow"


class EmojiConfig(BaseModel):
    """表情包学习系统配置"""
    enable_learning: bool = Field(default=True, description="是否开启学习模式")
    enable_sending: bool = Field(default=True, description="是否开启发送模式")
    sending_probability: float = Field(default=0.2, description="低相似度时的发送概率（0.0-1.0）")
    similarity_threshold: float = Field(default=0.3, description="最低检索相似度阈值")
    high_similarity_threshold: float = Field(default=0.4, description="高相似度阈值，超过此值直接发送")
    storage_path: str = Field(default="./emoji", description="表情包存储路径")
    retrieve_count: int = Field(default=1, description="每次检索返回的候选数量")
    send_delay: float = Field(default=1.0, description="发送延迟（秒）")
    
    class Config:
        extra = "allow"


class InjectionGuardConfig(BaseModel):
    """注入攻击防护配置"""
    enable: bool = Field(default=True, description="是否启用注入攻击防护")
    blacklist_minutes: int = Field(default=30, description="封禁时长（分钟）")
    guard_temperature: float = Field(default=0.1, description="审查模型温度")
    guard_timeout: int = Field(default=8, description="审查模型超时时间（秒）")
    enable_in_group_only_to_me: bool = Field(default=True, description="群聊仅 @ 时启用")
    enable_only_for_whitelisted_chat: bool = Field(default=True, description="只对白名单对话启用")
    skip_short_message_length: int = Field(default=5, description="短消息跳过检查的长度阈值（降低到 5 避免短注入攻击）")
    
    class Config:
        extra = "allow"


class WhitelistConfig(BaseModel):
    """白名单配置"""
    enable: bool = Field(default=True, description="是否开启白名单模式")
    allow_all_private: bool = Field(default=False, description="是否允许所有私聊")
    allowed_users: List[int] = Field(default=[], description="允许的私聊用户 QQ 号列表")
    allowed_groups: List[int] = Field(default=[], description="允许的群号列表")
    
    class Config:
        extra = "allow"


class BotConfig(BaseModel):
    """机器人基础配置"""
    nickname: str = Field(default="Yuki", description="机器人昵称")
    command_start: List[str] = Field(default=["/", ""], description="指令前缀")
    admin_id: List[int] = Field(default=[], description="超级用户 QQ 号")
    group_id: List[int] = Field(default=[], description="允许的群号")
    reply_strategy: ReplyStrategyConfig = Field(default_factory=ReplyStrategyConfig, description="回复策略配置")
    storage: StorageConfig = Field(default_factory=StorageConfig, description="存储配置")
    emoji: EmojiConfig = Field(default_factory=EmojiConfig, description="表情包配置")
    whitelist: WhitelistConfig = Field(default_factory=WhitelistConfig, description="白名单配置")
    injection_guard: InjectionGuardConfig = Field(default_factory=InjectionGuardConfig, description="注入攻击防护配置")
    
    class Config:
        extra = "allow"


# ============ 新的 AI 模型配置模型 ============
class ProviderConfig(BaseModel):
    """API 供应商配置"""
    api_base: str = Field(..., description="API 基础 URL")
    api_key: str = Field(default="", description="API 密钥（可为空）")
    timeout: int = Field(default=60, description="请求超时时间")
    
    class Config:
        extra = "allow"


class CommonConfig(BaseModel):
    """全局 AI 配置"""
    default_provider: str = Field(default="siliconflow", description="默认供应商")
    timeout: int = Field(default=60, description="全局请求超时时间")
    # 兼容旧配置
    api_base: str = Field(default="", description="API 基础 URL（已废弃，用 providers）")
    api_key: str = Field(default="", description="API 密钥（已废弃，用 providers）")
    
    class Config:
        extra = "allow"


class OrganizerConfig(BaseModel):
    """场景整理模型配置（第一阶段）"""
    provider: str = Field(default="", description="使用的供应商（留空用默认）")
    model_name: str = Field(..., description="模型标识符")
    temperature: float = Field(default=0.3, description="温度参数")
    max_tokens: int = Field(default=500, description="最大 token 数")
    timeout: int = Field(default=60, description="请求超时时间")
    enabled: bool = Field(default=True, description="是否启用")
    system_prompt: str = Field(default="", description="场景整理的系统提示词模板")
    
    class Config:
        extra = "allow"


class GeneratorConfig(BaseModel):
    """回复生成模型配置（第二阶段）"""
    provider: str = Field(default="", description="使用的供应商（留空用默认）")
    model_name: str = Field(..., description="模型标识符")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int = Field(default=2000, description="最大 token 数")
    timeout: int = Field(default=120, description="请求超时时间")
    enabled: bool = Field(default=True, description="是否启用")
    
    class Config:
        extra = "allow"


class FallbackConfig(BaseModel):
    """错误处理和降级配置"""
    error_reply: str = Field(default="哎呀，我的大脑短路了，请稍后再试...", description="兜底回复")
    skip_organizer_on_failure: bool = Field(
        default=False,
        description="整理阶段失败时是否跳过"
    )
    
    class Config:
        extra = "allow"


class VisionConfig(BaseModel):
    """视觉模型配置"""
    provider: str = Field(default="", description="使用的供应商（留空用默认）")
    model_name: str = Field(..., description="视觉模型标识符")
    temperature: float = Field(default=0.3, description="温度参数")
    max_tokens: int = Field(default=100, description="最大 token 数")
    timeout: int = Field(default=30, description="请求超时时间")
    
    class Config:
        extra = "allow"


class VisionCaptionConfig(BaseModel):
    """图片描述配置（用于对话）"""
    enabled: bool = Field(default=True, description="是否启用图片识别参与对话")
    prompt: str = Field(
        default="请用一句到两句简短自然的中文口语，客观描述这张图片的主要内容和气氛。",
        description="图片描述提示词"
    )
    max_length: int = Field(default=80, description="描述最大长度")
    temperature: float = Field(default=0.3, description="温度参数")
    max_tokens: int = Field(default=100, description="最大 token 数")
    timeout: int = Field(default=30, description="请求超时时间")
    
    class Config:
        extra = "allow"


class GuardConfig(BaseModel):
    """注入攻击审查模型配置"""
    provider: str = Field(default="", description="使用的供应商（留空用默认）")
    model_name: str = Field(..., description="审查模型标识符")
    temperature: float = Field(default=0.1, description="温度参数")
    max_tokens: int = Field(default=10, description="最大 token 数")
    timeout: int = Field(default=8, description="请求超时时间")
    
    class Config:
        extra = "allow"


class AIModelConfig(BaseModel):
    """AI 模型总体配置（双模型链式 + 嵌入 + 视觉 + 审查 + 工具类）"""
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict, description="API 供应商配置")
    common: CommonConfig = Field(..., description="全局配置")
    organizer: OrganizerConfig = Field(..., description="场景整理模型")
    kb_organizer: Optional[OrganizerConfig] = Field(default=None, description="知识库整理模型（可选，默认使用 organizer 配置）")
    generator: GeneratorConfig = Field(..., description="回复生成模型")
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig, description="嵌入模型配置")
    vision: VisionConfig = Field(..., description="视觉模型配置")
    vision_caption: Optional[VisionCaptionConfig] = Field(
        default=None, description="图片描述配置（用于对话）"
    )
    guard: GuardConfig = Field(..., description="注入攻击审查模型配置")
    utility: Optional[GeneratorConfig] = Field(default=None, description="工具类模型配置（歌词总结等）")
    fallback: FallbackConfig = Field(default_factory=FallbackConfig, description="错误处理配置")
    
    class Config:
        extra = "allow"


# ============ 角色扮演配置模型（细化） ============
class PersonaConfig(BaseModel):
    """人物设定配置"""
    name: str = Field(default="Yuki", description="角色名称")
    nickname: str = Field(default="小雪", description="昵称")
    age: str = Field(default="18", description="年龄")
    personality: str = Field(default="", description="性格关键词（可选）")
    background: str = Field(default="", description="人物背景（可选）")
    description: str = Field(default="", description="详细的人物设定描述（可选，已移至 expression）")
    
    class Config:
        extra = "allow"


class ExpressionConfig(BaseModel):
    """表达方式配置"""
    speaking_style: str = Field(default="", description="说话风格")
    description: str = Field(default="", description="角色设定描述（可选，会覆盖 persona.description）")
    tone_of_voice: str = Field(default="", description="语气")
    punctuation_style: str = Field(default="", description="标点符号习惯")
    use_action_markers: bool = Field(default=True, description="是否使用动作描写")
    action_format: str = Field(default="asterisk", description="动作描写格式")
    reply_length_preference: str = Field(default="medium", description="回复长度偏好")
    reply_length_description: str = Field(default="", description="回复长度详细说明")
    filler_words: List[str] = Field(default=[], description="语气词列表")
    filler_frequency: str = Field(default="low", description="语气词使用频率")
    
    class Config:
        extra = "allow"


class RecentDialogueConfig(BaseModel):
    """最近对话配置"""
    private_max_rounds: int = Field(default=6, description="私聊最大对话轮数")
    group_max_rounds: int = Field(default=4, description="群聊最大对话轮数")
    max_chars: int = Field(default=400, description="最大字符数")
    
    class Config:
        extra = "allow"


class SystemPromptTemplate(BaseModel):
    """系统提示词模板配置"""
    template: str = Field(..., description="私聊模板字符串，包含占位符")
    group_template: str = Field(default="", description="群聊模板字符串，包含占位符")
    conversation_rules: str = Field(default="", description="对话规则文本")
    role_profile: str = Field(default="", description="角色核心设定（约100字）")
    memory_summary_prompt: str = Field(default="", description="记忆摘要提示词模板")
    
    class Config:
        extra = "allow"


class RolePlayConfig(BaseModel):
    """角色扮演配置（细化版）"""
    persona: PersonaConfig = Field(..., description="人物设定")
    expression: ExpressionConfig = Field(..., description="表达方式")
    system_prompt_template: SystemPromptTemplate = Field(..., description="系统提示词模板")
    recent_dialogue: RecentDialogueConfig = Field(
        default_factory=RecentDialogueConfig, 
        description="最近对话配置"
    )
    
    class Config:
        extra = "allow"


# ============ 统一配置对象 ============
class FullConfig(BaseModel):
    """完整配置对象，包含所有配置部分"""
    bot: BotConfig
    ai_models: AIModelConfig
    role_play: RolePlayConfig
    
    class Config:
        extra = "allow"



# ============ 音乐点歌配置模型 ============
from typing import Literal as TypingLiteral


class MusicPlatformConfig(BaseModel):
    """音乐平台配置"""
    enable: bool = Field(default=True, description="是否启用该平台")
    base_url: str = Field(default="", description="API 基础 URL")
    search_path: str = Field(default="", description="搜索接口路径")
    auth_token: str = Field(default="", description="鉴权 Token（可选）")
    
    class Config:
        extra = "allow"


class MusicGeneralConfig(BaseModel):
    """音乐插件通用配置"""
    default_platform: TypingLiteral["qq", "netease"] = Field(
        default="netease", description="默认使用的音乐平台"
    )
    
    class Config:
        extra = "allow"


class MusicConfig(BaseModel):
    """音乐点歌插件完整配置"""
    general: MusicGeneralConfig = Field(default_factory=MusicGeneralConfig)
    qq: MusicPlatformConfig = Field(default_factory=MusicPlatformConfig)
    netease: MusicPlatformConfig = Field(default_factory=MusicPlatformConfig)
    
    class Config:
        extra = "allow"


# ============ 歌词总结配置模型 ============
class MusicTextGeneralConfig(BaseModel):
    """歌词总结插件通用配置"""
    enable: bool = Field(default=True, description="是否启用歌词总结功能")
    max_chars: int = Field(default=180, description="总结字数上限")
    cooldown_seconds: int = Field(default=10, description="冷却时间（秒）")
    
    class Config:
        extra = "allow"


class MusicTextPromptConfig(BaseModel):
    """歌词总结提示词配置"""
    template: str = Field(default="", description="总结提示词模板")
    
    class Config:
        extra = "allow"


class MusicTextPlatformConfig(BaseModel):
    """歌词接口平台配置"""
    enable: bool = Field(default=True, description="是否启用该平台")
    base_url: str = Field(default="", description="API 基础 URL")
    lyrics_path: str = Field(default="", description="歌词接口路径")
    songmid_param: str = Field(default="songmid", description="QQ 音乐参数名")
    id_param: str = Field(default="id", description="网易云参数名")
    
    class Config:
        extra = "allow"


class MusicTextConfig(BaseModel):
    """歌词总结插件完整配置"""
    general: MusicTextGeneralConfig = Field(default_factory=MusicTextGeneralConfig)
    prompt: MusicTextPromptConfig = Field(default_factory=MusicTextPromptConfig)
    qq: MusicTextPlatformConfig = Field(default_factory=MusicTextPlatformConfig)
    netease: MusicTextPlatformConfig = Field(default_factory=MusicTextPlatformConfig)
    
    class Config:
        extra = "allow"
