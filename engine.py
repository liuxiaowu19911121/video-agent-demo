# engine.py
import subprocess
import asyncio
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
import imageio_ffmpeg
from models import RenderTree

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def build_full_html(render_tree: RenderTree) -> str:
    print("[Template Engine] 正在拼装完整的 HTML...")
    env = Environment(loader=FileSystemLoader('components'))
    html_fragments = []
    for i, scene in enumerate(render_tree.scenes):
        template = env.get_template(f"{scene.type}_scene.html")
        html_fragments.append(template.render(index=i, params=scene.params.model_dump(), duration=scene.duration))
    
    joined_fragments = "\n".join(html_fragments)
    offsets_js = ""
    for scene in render_tree.scenes:
        offsets_js += f"offsets.push(offsets[offsets.length - 1] + {scene.duration});\n        "
    
    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <script src="science-demo/js/gsap.min.js"></script>
      <style> 
        body {{ margin: 0; background: #2c2c2c; overflow: hidden; font-family: sans-serif; }} 
        .scene {{ position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
      </style>
      <script> window.sceneAnims = []; </script>
    </head>
    <body>
      {joined_fragments}
      <script>
        const tl = gsap.timeline({{ paused: true }});
        const offsets = [0];
        {offsets_js}
        window.sceneAnims.forEach((animFunc, idx) => {{ animFunc(tl, offsets[idx]); }});
        window.__timelines = {{ main: tl }};
        // 💡 核心修复：添加 return null; 防止 Playwright 序列化死锁
        window.__seekFrame = (t) => {{
            tl.seek(t);
            return null;
        }};
      </script>
    </body>
    </html>
    """
    return final_html

# engine.py (只替换 render_video 函数)

# engine.py (仅替换 render_video 函数)
async def render_video(html_content: str, duration: float, out_mp4: Path):
    print("[Renderer] 启动 Playwright 进行逐帧截图...")
    
    temp_dir = Path("temp_frames")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    html_path = Path("temp_render.html")
    html_path.write_text(html_content, encoding="utf-8")
    
    total_frames = int(duration * 24)
    fps = 24

    try:
        async with async_playwright() as p:
            # 💡 核心修复：加上禁止后台节流的参数，让浏览器以为自己在前台
            browser = await p.chromium.launch(
                headless=True, 
                args=[
                    "--no-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--disable-backgrounding-occluded-windows"
                ]
            )
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            
            page.on("console", lambda msg: print(f"👉 [浏览器] {msg.type}: {msg.text}"))
            page.on("pageerror", lambda err: print(f"❌ [浏览器报错] {err}"))

            await page.goto("file://" + str(html_path.resolve()), wait_until="domcontentloaded")
            await page.wait_for_function("() => typeof window.__seekFrame === 'function'")

            for i in range(total_frames):
                if i % 24 == 0:
                    print(f"  -> 正在截图: {i}/{total_frames} 帧...")
                    
                t = i / fps
                try:
                    # 💡 核心修复：用大括号包住，不返回任何值（返回 undefined）
                    await asyncio.wait_for(
                        page.evaluate(f"() => {{ window.__seekFrame({t}); }}"), 
                        timeout=10.0
                    )
                    await asyncio.sleep(0.02)
                except asyncio.TimeoutError:
                    print(f"❌ 拨动时间轴超时，卡在第 {i} 帧！")
                    raise RuntimeError(f"Frame {i} evaluate timeout")
                    
                frame_path = temp_dir / f"frame_{i:04d}.jpg"
                await page.screenshot(path=frame_path, type="jpeg", quality=85)

        print(f"[Renderer] 截图完成，正在调用 FFmpeg 合成视频...")
        ffmpeg_cmd = [
            FFMPEG_EXE, "-y", "-framerate", str(fps), 
            "-i", str(temp_dir / "frame_%04d.jpg"), 
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out_mp4)
        ]
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"[Renderer] ✅ 渲染完成: {out_mp4}")
        
    finally:
        #if html_path.exists(): html_path.unlink()
        if temp_dir.exists(): shutil.rmtree(temp_dir)