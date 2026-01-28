"""API routes - OpenAI compatible endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from datetime import datetime
from typing import List
import json
import re
import traceback
from ..core.auth import verify_api_key_header
from ..core.logger import debug_logger
from ..core.models import (
    ChatCompletionRequest,
    ImageGenerateRequest,
    ImageTransformRequest,
    VideoGenerateRequest,
    VideoTransformRequest,
    VideoRemixRequest,
    VideoStoryboardRequest,
    CharacterCreateRequest,
    CharacterGenerateRequest,
    TaskStatusResponse
)
from ..services.generation_handler import GenerationHandler, MODEL_CONFIG

router = APIRouter()

# Dependency injection will be set up in main.py
generation_handler: GenerationHandler = None

def set_generation_handler(handler: GenerationHandler):
    """Set generation handler instance"""
    global generation_handler
    generation_handler = handler

def _log_exception(endpoint: str, exception: Exception):
    """Log exception with full traceback"""
    error_traceback = traceback.format_exc()
    debug_logger.log_api_error(
        path=endpoint,
        error_message=str(exception),
        status_code=500,
        traceback_str=error_traceback
    )

def _extract_remix_id(text: str) -> str:
    """Extract remix ID from text

    Supports two formats:
    1. Full URL: https://sora.chatgpt.com/p/s_68e3a06dcd888191b150971da152c1f5
    2. Short ID: s_68e3a06dcd888191b150971da152c1f5

    Args:
        text: Text to search for remix ID

    Returns:
        Remix ID (s_[a-f0-9]{32}) or empty string if not found
    """
    if not text:
        return ""

    # Match Sora share link format: s_[a-f0-9]{32}
    match = re.search(r's_[a-f0-9]{32}', text)
    if match:
        return match.group(0)

    return ""

@router.get("/v1/models")
async def list_models(api_key: str = Depends(verify_api_key_header)):
    """List available models"""
    models = []
    
    for model_id, config in MODEL_CONFIG.items():
        models.append({
            "id": model_id,
            "object": "model"
        })
    
    return {
        "object": "list",
        "data": models
    }

@router.get("/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    api_key: str = Depends(verify_api_key_header)
):
    """查询任务状态 - 统一的任务查询接口
    
    用于查询图片和视频生成任务的状态和结果
    
    Args:
        task_id: 任务ID（从生成接口返回）
        
    Returns:
        TaskStatusResponse: 任务状态信息
    """
    try:
        # 从数据库获取任务
        task = await generation_handler.db.get_task(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # 解析 result_urls
        result_urls = None
        if task.result_urls:
            try:
                parsed_result = json.loads(task.result_urls)
                # Check if this is a character creation task (returns dict instead of list)
                if task.model == "character-creation":
                    # For character creation, result_urls is a dict with character info
                    # TaskStatusResponse now supports Union[List[str], Dict]
                    if isinstance(parsed_result, dict):
                        result_urls = parsed_result  # Keep as dict
                    else:
                        result_urls = parsed_result if isinstance(parsed_result, list) else [parsed_result]
                else:
                    # For other task types (image/video), result_urls should be a list
                    result_urls = parsed_result if isinstance(parsed_result, list) else [parsed_result]
            except:
                result_urls = [task.result_urls] if task.result_urls else None
        
        return TaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            progress=task.progress,
            model=task.model,
            prompt=task.prompt,
            result_urls=result_urls,
            error_message=task.error_message,
            created_at=task.created_at.isoformat() if task.created_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v1/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """Create chat completion (unified endpoint for image and video generation)"""
    try:
        # 检查 generation_handler 是否已初始化
        if generation_handler is None:
            raise HTTPException(status_code=500, detail="Generation handler not initialized")
        
        # Extract prompt from messages
        if not request.messages:
            raise HTTPException(status_code=400, detail="Messages cannot be empty")

        last_message = request.messages[-1]
        content = last_message.content

        # Handle both string and array format (OpenAI multimodal)
        prompt = ""
        image_data = request.image  # Default to request.image if provided
        video_data = request.video  # Video parameter
        remix_target_id = request.remix_target_id  # Remix target ID

        if isinstance(content, str):
            # Simple string format
            prompt = content
            # Extract remix_target_id from prompt if not already provided
            if not remix_target_id:
                remix_target_id = _extract_remix_id(prompt)
        elif isinstance(content, list):
            # Array format (OpenAI multimodal)
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        prompt = item.get("text", "")
                        # Extract remix_target_id from prompt if not already provided
                        if not remix_target_id:
                            remix_target_id = _extract_remix_id(prompt)
                    elif item.get("type") == "image_url":
                        # Extract base64 image from data URI
                        image_url = item.get("image_url", {})
                        url = image_url.get("url", "")
                        if url.startswith("data:image"):
                            # Extract base64 data from data URI
                            if "base64," in url:
                                image_data = url.split("base64,", 1)[1]
                            else:
                                image_data = url
                    elif item.get("type") == "video_url":
                        # Extract video from video_url
                        video_url = item.get("video_url", {})
                        url = video_url.get("url", "")
                        if url.startswith("data:video") or url.startswith("data:application"):
                            # Extract base64 data from data URI
                            if "base64," in url:
                                video_data = url.split("base64,", 1)[1]
                            else:
                                video_data = url
                        else:
                            # It's a URL, pass it as-is (will be downloaded in generation_handler)
                            video_data = url
        else:
            raise HTTPException(status_code=400, detail="Invalid content format")

        # Validate model
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")

        # Check if this is a video model
        model_config = MODEL_CONFIG[request.model]
        is_video_model = model_config["type"] == "video"

        # For video models with video parameter, we need streaming
        if is_video_model and (video_data or remix_target_id):
            if not request.stream:
                # Non-streaming mode: only check availability
                result = None
                async for chunk in generation_handler.handle_generation(
                    model=request.model,
                    prompt=prompt,
                    image=image_data,
                    video=video_data,
                    remix_target_id=remix_target_id,
                    stream=False
                ):
                    result = chunk

                if result:
                    return JSONResponse(content=json.loads(result))
                else:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": {
                                "message": "Availability check failed",
                                "type": "server_error",
                                "param": None,
                                "code": None
                            }
                        }
                    )

        # Handle streaming
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=prompt,
                        image=image_data,
                        video=video_data,
                        remix_target_id=remix_target_id,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    # Try to parse structured error (JSON format)
                    error_data = None
                    try:
                        error_data = json.loads(str(e))
                    except:
                        pass

                    # Return OpenAI-compatible error format
                    if error_data and isinstance(error_data, dict) and "error" in error_data:
                        # Structured error (e.g., unsupported_country_code)
                        error_response = error_data
                    else:
                        # Generic error
                        error_response = {
                            "error": {
                                "message": str(e),
                                "type": "server_error",
                                "param": None,
                                "code": None
                            }
                        }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # Non-streaming response (availability check only)
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=prompt,
                image=image_data,
                video=video_data,
                remix_target_id=remix_target_id,
                stream=False
            ):
                result = chunk

            if result:
                return JSONResponse(content=json.loads(result))
            else:
                # Return OpenAI-compatible error format
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Availability check failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )

    except Exception as e:
        # Return OpenAI-compatible error format
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

# ==================== 独立功能 API 端点 ====================

@router.post("/v1/images/generate")
async def generate_image(
    request: ImageGenerateRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """文生图 - 根据文本描述生成图片"""
    try:
        # 检查 generation_handler 是否已初始化
        if generation_handler is None:
            raise HTTPException(status_code=500, detail="Generation handler not initialized")
        
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "image":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not an image model")
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_generation_task(
                model=request.model,
                prompt=request.prompt,
                image=None,
                video=None,
                remix_target_id=None
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=request.prompt,
                        image=None,
                        video=None,
                        remix_target_id=None,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=request.prompt,
                image=None,
                video=None,
                remix_target_id=None,
                stream=False
            ):
                result = chunk
            
            if result:
                return JSONResponse(content=json.loads(result))
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Generation failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

@router.post("/v1/images/transform")
async def transform_image(
    request: ImageTransformRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """图生图 - 基于上传的图片进行创意变换"""
    try:
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "image":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not an image model")
        
        # 提取 base64 图片数据
        image_data = request.image
        if image_data.startswith("data:image"):
            if "base64," in image_data:
                image_data = image_data.split("base64,", 1)[1]
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_generation_task(
                model=request.model,
                prompt=request.prompt,
                image=image_data,
                video=None,
                remix_target_id=None
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=request.prompt,
                        image=image_data,
                        video=None,
                        remix_target_id=None,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=request.prompt,
                image=image_data,
                video=None,
                remix_target_id=None,
                stream=False
            ):
                result = chunk
            
            if result:
                return JSONResponse(content=json.loads(result))
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Generation failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

@router.post("/v1/videos/generate")
async def generate_video(
    request: VideoGenerateRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """文生视频 - 根据文本描述生成视频"""
    try:
        # 检查 generation_handler 是否已初始化
        if generation_handler is None:
            raise HTTPException(status_code=500, detail="Generation handler not initialized")
        
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "video":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not a video model")
        
        # 处理风格
        prompt = request.prompt
        if request.style:
            prompt = f"{{{request.style}}}{prompt}"
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_generation_task(
                model=request.model,
                prompt=prompt,
                image=None,
                video=None,
                remix_target_id=None
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=prompt,
                        image=None,
                        video=None,
                        remix_target_id=None,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=prompt,
                image=None,
                video=None,
                remix_target_id=None,
                stream=False
            ):
                result = chunk
            
            if result:
                return JSONResponse(content=json.loads(result))
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Generation failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        # Log the exception with full traceback
        _log_exception("/v1/videos/generate", e)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

@router.post("/v1/videos/transform")
async def transform_video(
    request: VideoTransformRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """图生视频 - 基于图片生成相关视频"""
    try:
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "video":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not a video model")
        
        # 提取 base64 图片数据
        image_data = request.image
        if image_data.startswith("data:image"):
            if "base64," in image_data:
                image_data = image_data.split("base64,", 1)[1]
        
        # 处理风格
        prompt = request.prompt
        if request.style:
            prompt = f"{{{request.style}}}{prompt}"
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_generation_task(
                model=request.model,
                prompt=prompt,
                image=image_data,
                video=None,
                remix_target_id=None
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=prompt,
                        image=image_data,
                        video=None,
                        remix_target_id=None,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=prompt,
                image=image_data,
                video=None,
                remix_target_id=None,
                stream=False
            ):
                result = chunk
            
            if result:
                return JSONResponse(content=json.loads(result))
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Generation failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

@router.post("/v1/videos/remix")
async def remix_video(
    request: VideoRemixRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """Remix 视频 - 基于已有视频继续创作"""
    try:
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "video":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not a video model")
        
        # 处理风格
        prompt = request.prompt
        if request.style:
            prompt = f"{{{request.style}}}{prompt}"
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_generation_task(
                model=request.model,
                prompt=prompt,
                image=None,
                video=None,
                remix_target_id=request.remix_target_id
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=prompt,
                        image=None,
                        video=None,
                        remix_target_id=request.remix_target_id,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=prompt,
                image=None,
                video=None,
                remix_target_id=request.remix_target_id,
                stream=False
            ):
                result = chunk
            
            if result:
                return JSONResponse(content=json.loads(result))
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Generation failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

@router.post("/v1/videos/storyboard")
async def storyboard_video(
    request: VideoStoryboardRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """视频分镜 - 生成分镜视频"""
    try:
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "video":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not a video model")
        
        # 处理风格
        prompt = request.prompt
        if request.style:
            prompt = f"{{{request.style}}}{prompt}"
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_generation_task(
                model=request.model,
                prompt=prompt,
                image=None,
                video=None,
                remix_target_id=None
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler.handle_generation(
                        model=request.model,
                        prompt=prompt,
                        image=None,
                        video=None,
                        remix_target_id=None,
                        stream=True
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            result = None
            async for chunk in generation_handler.handle_generation(
                model=request.model,
                prompt=prompt,
                image=None,
                video=None,
                remix_target_id=None,
                stream=False
            ):
                result = chunk
            
            if result:
                return JSONResponse(content=json.loads(result))
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "message": "Generation failed",
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )

@router.post("/v1/characters/create")
async def create_character(
    request: CharacterCreateRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """创建角色 - 上传视频提取角色信息"""
    # 检查 generation_handler 是否已初始化
    if generation_handler is None:
        raise HTTPException(status_code=500, detail="Generation handler not initialized")
    
    try:
        # 提取视频数据（支持 base64 或 URL）
        video_data = request.video
        if video_data.startswith("http://") or video_data.startswith("https://"):
            # 这是 URL，直接传递
            pass
        elif video_data.startswith("data:video") or video_data.startswith("data:application"):
            # 这是 base64 data URI，提取 base64 数据
            if "base64," in video_data:
                video_data = video_data.split("base64,", 1)[1]
        
        # 异步模式：立即返回 task_id
        if request.async_mode:
            task_id, task_type = await generation_handler.submit_character_creation_task(
                video_data=video_data,
                timestamps=request.timestamps
            )
            return JSONResponse(content={
                "task_id": task_id,
                "task_type": task_type,
                "status": "processing",
                "message": "Task submitted successfully. Use GET /v1/tasks/{task_id} to check status."
            })
        
        # 使用默认的视频模型配置
        model_config = MODEL_CONFIG["sora2-landscape-10s"]
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    # 确保生成器立即开始产生数据
                    async for chunk in generation_handler._handle_character_creation_only(
                        video_data=video_data,
                        model_config=model_config,
                        timestamps=request.timestamps
                    ):
                        yield chunk
                except Exception as e:
                    # 确保错误也被正确发送
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
                finally:
                    # 确保流式响应正确结束
                    pass
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应不支持角色创建（因为需要流式输出角色名）
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": "Character creation requires streaming mode. Please set stream=true",
                        "type": "invalid_request_error",
                        "param": "stream",
                        "code": None
                    }
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        # 如果是在流式响应之前出错，返回 JSON 响应
        if not request.stream:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(e),
                        "type": "server_error",
                        "param": None,
                        "code": None
                    }
                }
            )
        # 如果是在流式响应中出错，需要通过生成器处理
        async def error_generate():
            error_response = {
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
            yield f'data: {json.dumps(error_response)}\n\n'
            yield 'data: [DONE]\n\n'
        
        return StreamingResponse(
            error_generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

@router.post("/v1/characters/generate")
async def generate_character_video(
    request: CharacterGenerateRequest,
    api_key: str = Depends(verify_api_key_header)
):
    """角色生成视频 - 创建角色并使用角色生成视频"""
    try:
        # 验证模型
        if request.model not in MODEL_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
        
        model_config = MODEL_CONFIG[request.model]
        if model_config["type"] != "video":
            raise HTTPException(status_code=400, detail=f"Model {request.model} is not a video model")
        
        # 提取视频数据（支持 base64 或 URL）
        video_data = request.video
        if video_data.startswith("http://") or video_data.startswith("https://"):
            # 这是 URL，直接传递
            pass
        elif video_data.startswith("data:video") or video_data.startswith("data:application"):
            # 这是 base64 data URI，提取 base64 数据
            if "base64," in video_data:
                video_data = video_data.split("base64,", 1)[1]
        
        # 处理流式响应
        if request.stream:
            async def generate():
                try:
                    async for chunk in generation_handler._handle_character_and_video_generation(
                        video_data=video_data,
                        prompt=request.prompt,
                        model_config=model_config,
                        timestamps=request.timestamps
                    ):
                        yield chunk
                except Exception as e:
                    error_response = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "param": None,
                            "code": None
                        }
                    }
                    error_chunk = f'data: {json.dumps(error_response)}\n\n'
                    yield error_chunk
                    yield 'data: [DONE]\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应不支持角色生成视频（因为需要流式输出）
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": "Character video generation requires streaming mode. Please set stream=true",
                        "type": "invalid_request_error",
                        "param": "stream",
                        "code": None
                    }
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }
        )
