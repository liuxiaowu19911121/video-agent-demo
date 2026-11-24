# mcp_server.py
import asyncio
import uuid
# 🔄 适配 mcp 2.x：导入 MCPServer 替代 FastMCP
from mcp.server.mcpserver import MCPServer
from video_renderer import execute_full_pipeline

# 初始化 MCP Server（使用新的类名 MCPServer）
mcp = MCPServer("Video-Generator-Agent")

# 模拟的任务数据库和并发锁
tasks_db = {}
render_semaphore = asyncio.Semaphore(1)

@mcp.tool()
async def generate_video(topic: str) -> str:
    """
    根据用户提供的科普主题，生成一条带旁白的白盒代码渲染视频。
    返回任务的 ID，上层 Agent 可通过 ID 查询进度。
    """
    task_id = str(uuid.uuid4())[:8]
    tasks_db[task_id] = {"status": "queued", "progress": 0, "topic": topic}
    
    # 异步启动渲染任务
    asyncio.create_task(execute_full_pipeline(task_id, topic, tasks_db, render_semaphore))
    
    return f"视频渲染任务已提交。任务ID: {task_id}。请稍后通过任务ID查询结果。"

@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """查询视频渲染任务的当前状态和可观测性指标"""
    if task_id not in tasks_db:
        return {"error": "任务不存在"}
    return tasks_db[task_id]

if __name__ == "__main__":
    # 使用 stdio 传输协议启动 MCP Server
    mcp.run()