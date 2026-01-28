"""Data models"""
from datetime import datetime
from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel

class Token(BaseModel):
    """Token model"""
    id: Optional[int] = None
    token: str
    email: str
    name: Optional[str] = ""
    st: Optional[str] = None
    rt: Optional[str] = None
    client_id: Optional[str] = None
    proxy_url: Optional[str] = None
    remark: Optional[str] = None
    expiry_time: Optional[datetime] = None
    is_active: bool = True
    cooled_until: Optional[datetime] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    # 订阅信息
    plan_type: Optional[str] = None  # 账户类型，如 chatgpt_team
    plan_title: Optional[str] = None  # 套餐名称，如 ChatGPT Business
    subscription_end: Optional[datetime] = None  # 套餐到期时间
    # Sora2 支持信息
    sora2_supported: Optional[bool] = None  # 是否支持Sora2
    sora2_invite_code: Optional[str] = None  # Sora2邀请码
    sora2_redeemed_count: int = 0  # Sora2已用次数
    sora2_total_count: int = 0  # Sora2总次数
    # Sora2 剩余次数
    sora2_remaining_count: int = 0  # Sora2剩余可用次数
    sora2_cooldown_until: Optional[datetime] = None  # Sora2冷却时间
    # 功能开关
    image_enabled: bool = True  # 是否启用图片生成
    video_enabled: bool = True  # 是否启用视频生成
    # 并发限制
    image_concurrency: int = -1  # 图片并发数限制，-1表示不限制
    video_concurrency: int = -1  # 视频并发数限制，-1表示不限制
    # 过期标记
    is_expired: bool = False  # Token是否已过期（401 token_invalidated）

class TokenStats(BaseModel):
    """Token statistics"""
    id: Optional[int] = None
    token_id: int
    image_count: int = 0
    video_count: int = 0
    error_count: int = 0  # Historical total errors (never reset)
    last_error_at: Optional[datetime] = None
    today_image_count: int = 0
    today_video_count: int = 0
    today_error_count: int = 0
    today_date: Optional[str] = None
    consecutive_error_count: int = 0  # Consecutive errors for auto-disable

class Task(BaseModel):
    """Task model"""
    id: Optional[int] = None
    task_id: str
    token_id: int
    model: str
    prompt: str
    status: str = "processing"  # processing/completed/failed
    progress: float = 0.0
    result_urls: Optional[str] = None  # JSON array
    error_message: Optional[str] = None
    retry_count: int = 0  # 当前重试次数
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class RequestLog(BaseModel):
    """Request log model"""
    id: Optional[int] = None
    token_id: Optional[int] = None
    task_id: Optional[str] = None  # Link to task for progress tracking
    operation: str
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    status_code: int  # -1 for in-progress
    duration: float  # -1.0 for in-progress
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class AdminConfig(BaseModel):
    """Admin configuration"""
    id: int = 1
    admin_username: str  # Read from database, initialized from setting.toml on first startup
    admin_password: str  # Read from database, initialized from setting.toml on first startup
    api_key: str  # Read from database, initialized from setting.toml on first startup
    error_ban_threshold: int = 3
    task_retry_enabled: bool = True  # 是否启用任务失败重试
    task_max_retries: int = 3  # 任务最大重试次数
    auto_disable_on_401: bool = True  # 遇到401错误自动禁用token
    updated_at: Optional[datetime] = None

class ProxyConfig(BaseModel):
    """Proxy configuration"""
    id: int = 1
    proxy_enabled: bool  # Read from database, initialized from setting.toml on first startup
    proxy_url: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class WatermarkFreeConfig(BaseModel):
    """Watermark-free mode configuration"""
    id: int = 1
    watermark_free_enabled: bool  # Read from database, initialized from setting.toml on first startup
    parse_method: str  # Read from database, initialized from setting.toml on first startup
    custom_parse_url: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    custom_parse_token: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    fallback_on_failure: bool = True  # Auto fallback to watermarked video on failure, default True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CacheConfig(BaseModel):
    """Cache configuration"""
    id: int = 1
    cache_enabled: bool  # Read from database, initialized from setting.toml on first startup
    cache_timeout: int  # Read from database, initialized from setting.toml on first startup
    cache_base_url: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class GenerationConfig(BaseModel):
    """Generation timeout configuration"""
    id: int = 1
    image_timeout: int  # Read from database, initialized from setting.toml on first startup
    video_timeout: int  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TokenRefreshConfig(BaseModel):
    """Token refresh configuration"""
    id: int = 1
    at_auto_refresh_enabled: bool  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CallLogicConfig(BaseModel):
    """Call logic configuration"""
    id: int = 1
    call_mode: str = "default"  # "default" or "polling"
    polling_mode_enabled: bool = False  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# API Request/Response models
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[dict]]  # Support both string and array format (OpenAI multimodal)

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    image: Optional[str] = None
    video: Optional[str] = None  # Base64 encoded video file
    remix_target_id: Optional[str] = None  # Sora share link video ID for remix
    stream: bool = False
    max_tokens: Optional[int] = None

class ChatCompletionChoice(BaseModel):
    index: int
    message: Optional[dict] = None
    delta: Optional[dict] = None
    finish_reason: Optional[str] = None

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]

# New API Request Models
class ImageGenerateRequest(BaseModel):
    """文生图请求"""
    prompt: str
    model: str = "gpt-image"  # gpt-image, gpt-image-landscape, gpt-image-portrait
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果

class ImageTransformRequest(BaseModel):
    """图生图请求"""
    prompt: str
    image: str  # Base64 encoded image
    model: str = "gpt-image"  # gpt-image, gpt-image-landscape, gpt-image-portrait
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果

class VideoGenerateRequest(BaseModel):
    """文生视频请求"""
    prompt: str
    model: str = "sora2-landscape-10s"  # sora2-* models
    style: Optional[str] = None  # 风格ID，如 anime, retro 等
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果

class VideoTransformRequest(BaseModel):
    """图生视频请求"""
    prompt: str
    image: str  # Base64 encoded image
    model: str = "sora2-landscape-10s"  # sora2-* models
    style: Optional[str] = None  # 风格ID，如 anime, retro 等
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果

class VideoRemixRequest(BaseModel):
    """Remix 视频请求"""
    prompt: str
    remix_target_id: str  # Sora share link video ID (s_xxx)
    model: str = "sora2-landscape-10s"  # sora2-* models
    style: Optional[str] = None  # 风格ID，如 anime, retro 等
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果

class VideoStoryboardRequest(BaseModel):
    """视频分镜请求"""
    prompt: str  # 分镜格式：```[时长s]提示词``` 或 [时长s]提示词
    model: str = "sora2-landscape-10s"  # sora2-* models
    style: Optional[str] = None  # 风格ID，如 anime, retro 等
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果

class CharacterCreateRequest(BaseModel):
    """创建角色请求"""
    video: str  # Base64 encoded video or video URL
    stream: bool = False
    async_mode: bool = False  # 异步模式：立即返回task_id，不等待结果，通过 /v1/tasks/{task_id} 查询状态
    timestamps: Optional[str] = "0,3"  # 视频时间戳，格式如 "0,3" 表示从0秒到3秒

class CharacterGenerateRequest(BaseModel):
    """角色生成视频请求"""
    prompt: str
    video: str  # Base64 encoded video or video URL
    model: str = "sora2-landscape-10s"  # sora2-* models
    stream: bool = False
    timestamps: Optional[str] = "0,3"  # 视频时间戳，格式如 "0,3" 表示从0秒到3秒

class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str  # processing/completed/failed
    progress: float  # 0.0-100.0
    model: str
    prompt: str
    result_urls: Optional[Union[List[str], Dict[str, Any]]] = None  # 结果URL列表或角色信息字典
    error_message: Optional[str] = None  # 错误信息（如果有）
    created_at: Optional[str] = None  # ISO格式时间戳
    completed_at: Optional[str] = None  # ISO格式时间戳
