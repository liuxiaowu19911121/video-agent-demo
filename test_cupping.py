import asyncio
import subprocess
from pathlib import Path
import imageio_ffmpeg
from playwright.async_api import async_playwright

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
WIDTH, HEIGHT, FPS = 1920, 1080, 24

async def render_cupping():
    duration = 5.0  # 测试 5 秒的视频
    total_frames = int(duration * FPS)
    html_path = Path("science-demo/cupping.html").resolve()
    out_mp4 = Path("renders/cupping_test.mp4")
    out_mp4.parent.mkdir(exist_ok=True)

    # 启动 FFmpeg 接收管道流
    ffmpeg_cmd = [
        FFMPEG_EXE, "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
        str(out_mp4)
    ]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        await page.goto(f"file://{html_path}", wait_until="domcontentloaded")
        
        # 等待 GSAP 就绪
        await page.wait_for_function("() => typeof window.__seekFrame === 'function'")

        print(f"开始渲染拔火罐 Demo ({total_frames} 帧)...")
        for i in range(total_frames):
            t = i / FPS
            await page.evaluate("(time) => window.__seekFrame(time)", t)
            await page.evaluate("() => new Promise(requestAnimationFrame)")
            
            frame_bytes = await page.screenshot(type="jpeg", quality=85)
            ffmpeg_proc.stdin.write(frame_bytes)
            
            if i % 24 == 0:
                print(f"  -> 渲染帧: {i}/{total_frames}")

        await browser.close()

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    print("✅ 渲染完成: renders/cupping_test.mp4")

if __name__ == "__main__":
    asyncio.run(render_cupping())