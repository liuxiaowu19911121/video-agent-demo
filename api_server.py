# api_server.py
import uuid
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from video_renderer import execute_full_pipeline

app = FastAPI(title="视频生成 Agent 基础架构 API")

# 模拟 Redis 数据库，记录状态
tasks_db = {}

# 🚦 全局信号量：在 4核4G 环境下，最大并发渲染数严格限制为 1
MAX_CONCURRENT_RENDERS = 1
render_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)

class GenerateRequest(BaseModel):
    topic: str

@app.post("/api/v1/generate")
async def generate_video(request: GenerateRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    
    # 1. 记录初始状态
    tasks_db[task_id] = {
        "status": "queued",
        "progress": 0,
        "topic": request.topic,
        "video_path": None,
        "error": None
    }
    
    # 2. 丢入后台任务队列，立刻返回 task_id (削峰填谷)
    background_tasks.add_task(
        execute_full_pipeline, 
        task_id=task_id, 
        topic=request.topic, 
        task_db=tasks_db, 
        semaphore=render_semaphore
    )
    
    return {"code": 200, "message": "任务已受理", "task_id": task_id}

@app.get("/api/v1/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks_db:
        return {"code": 404, "message": "任务不存在"}
    return {"code": 200, "data": tasks_db[task_id]}

@app.get("/api/v1/download/{task_id}")
async def download_video(task_id: str):
    task = tasks_db.get(task_id)
    if not task or task["status"] != "completed":
        return {"code": 400, "message": "视频未就绪或不存在"}
    return FileResponse(task["video_path"], media_type="video/mp4", filename=f"{task_id}.mp4")