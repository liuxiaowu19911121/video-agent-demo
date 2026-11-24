import asyncio
import subprocess
from pathlib import Path
import imageio_ffmpeg
from playwright.async_api import async_playwright

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

html_content = """
<!DOCTYPE html>
<html>
<head>
  <style> body { margin: 0; background: #2c2c2c; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; font-size: 80px; } </style>
</head>
<body>
  <h1>Hello Video!</h1>
</body>
</html>
"""

async def main():
    html_path = Path("test_static.html")
    html_path.write_text(html_content, encoding="utf-8")
    out_mp4 = Path("renders/test_static.mp4")
    
    async with async_playwright() as p:
        print("启动浏览器...")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        
        print("加载页面...")
        await page.goto("file://" + str(html_path.resolve()))
        
        print("开始截图...")
        for i in range(10):  # 只截图 10 帧
            print(f"截取第 {i} 帧...")
            frame_path = Path(f"temp_frames/test_{i:04d}.jpg")
            frame_path.parent.mkdir(exist_ok=True)
            await page.screenshot(path=frame_path, type="jpeg")
            
        await browser.close()
        print("浏览器已关闭。")

    print("调用 FFmpeg...")
    subprocess.run([FFMPEG_EXE, "-y", "-framerate", "24", "-i", "temp_frames/test_%04d.jpg", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_mp4)])
    print("✅ 静态测试跑通！")

if __name__ == "__main__":
    asyncio.run(main())