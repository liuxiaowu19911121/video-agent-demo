# main.py
import asyncio
from pathlib import Path
from agents.director import generate_script
from agents.planner import plan_render_tree
from engine import build_full_html, render_video

async def main():
    topic = "拔火罐原理科普"
    script = generate_script(topic)
    render_tree = plan_render_tree(script)
    full_html = build_full_html(render_tree)
    
    total_duration = sum([s.duration for s in render_tree.scenes])
    await render_video(full_html, total_duration, Path("renders/pipeline_demo.mp4"))
    
    # 注释掉后台任务和等待，只测渲染！
    # print("\n[Main] 主任务完成，等待后台 Agent 进化...")
    # await asyncio.sleep(10)
    print("[Main] 主进程安全退出。")

if __name__ == "__main__":
    asyncio.run(main())