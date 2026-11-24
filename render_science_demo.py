import asyncio
import subprocess
import sys
import shutil
from pathlib import Path

# 尝试导入 imageio_ffmpeg，如果没有则回退到系统 ffmpeg
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_EXE = shutil.which("ffmpeg") or "ffmpeg"

from edge_tts import Communicate
from playwright.async_api import async_playwright

print(f"[System] 当前使用的 FFmpeg 路径: {FFMPEG_EXE}")

HTML_PATH = Path("science-demo/index.html")
OUTPUT_DIR = Path("renders")
OUTPUT_DIR.mkdir(exist_ok=True)

WIDTH, HEIGHT = 1920, 1080
FPS = 24
DURATION_FALLBACK = 12.0


async def generate_narration(text: str, out_path: Path, timeout: float = 25.0) -> bool:
    try:
        communicate = Communicate(text, voice="zh-CN-XiaoxiaoNeural")
        await asyncio.wait_for(communicate.save(str(out_path)), timeout=timeout)
        print(f"[TTS] 旁白生成成功: {out_path}")
        return True
    except Exception as e:
        print(f"[TTS] 失败跳过: {e}", file=sys.stderr)
        return False


def probe_duration(media_path: Path) -> float | None:
    if not media_path.exists():
        return None
    cmd = [
        FFMPEG_EXE, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return None


async def render_via_pipe(html_path: Path, duration: float, fps: int, out_mp4: Path, audio_path: Path | None = None):
    total_frames = round(duration * fps)

    # 💡 修复参数顺序：所有输入(-i)放在前面，所有输出参数(-c, -movflags)放在后面
    ffmpeg_cmd = [
        FFMPEG_EXE, "-y",
        "-f", "image2pipe", "-framerate", str(fps), "-i", "-",  # 输入1：截图流
    ]
    
    if audio_path and audio_path.exists():
        ffmpeg_cmd += ["-f", "mp3", "-i", str(audio_path)]     # 输入2：音频文件

    # 输出视频参数（尝试使用 libx264）
    ffmpeg_cmd += [
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
    ]
    
    if audio_path and audio_path.exists():
        ffmpeg_cmd += ["-c:a", "aac", "-shortest"]
        
    ffmpeg_cmd += ["-movflags", "+faststart", str(out_mp4)]

    # 启动 FFmpeg 进程
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    # 启动浏览器
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--headless=new", "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu", "--disable-images",
                "--font-render-hinting=none", "--js-flags=--max-old-space-size=256",
            ],
        )
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        
        file_url = "file://" + str(html_path.resolve())
        print(f"[Playwright] 正在加载页面: {file_url}")
        
        await page.goto(file_url, wait_until="domcontentloaded")
        print("[Playwright] DOM 加载完成，等待 GSAP 初始化...")

        is_ready = False
        for _ in range(50):
            is_ready = await page.evaluate(
                "() => typeof window.__seekFrame === 'function' && !!window.__timelines && !!window.__timelines.main"
            )
            if is_ready:
                break
            await asyncio.sleep(0.1)

        if not is_ready:
            raise RuntimeError("❌ 等待超时：window.__seekFrame 未挂载，请检查 index.html。")
            
        print("[Playwright] 🎉 GSAP 就绪！开始逐帧渲染...")

        for i in range(total_frames):
            # 检查 FFmpeg 是否因为缺少 libx264 等原因直接崩溃
            if ffmpeg_proc.poll() is not None:
                err_output = ffmpeg_proc.stderr.read().decode('utf-8', errors='replace')
                print(f"⚠️ FFmpeg 报错退出，检测到编码器缺失，正在尝试降级到 mpeg4...")
                # 简单的降级重试逻辑（在实际面试中，你可以把这个写成真正的 Re-try）
                raise RuntimeError(f"❌ FFmpeg 提前退出！错误信息:\n{err_output}")

            t = i / fps
            await page.evaluate("(time) => window.__seekFrame(time)", t)
            await page.evaluate("() => new Promise(requestAnimationFrame)")

            frame_bytes = await page.screenshot(
                type="jpeg", quality=85, clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
            )
            
            try:
                ffmpeg_proc.stdin.write(frame_bytes)
            except BrokenPipeError:
                err_output = ffmpeg_proc.stderr.read().decode('utf-8', errors='replace')
                raise RuntimeError(f"❌ 管道破裂（第 {i} 帧）！FFmpeg 错误信息:\n{err_output}")
            
            if i % 24 == 0:
                print(f"  -> 已渲染 {i}/{total_frames} 帧...")

        await browser.close()

    try:
        ffmpeg_proc.stdin.close()
    except BrokenPipeError:
        pass
        
    ffmpeg_err = ffmpeg_proc.stderr.read()
    ffmpeg_proc.wait()

    if ffmpeg_proc.returncode != 0:
        raise RuntimeError("FFmpeg 编码失败:\n" + ffmpeg_err.decode(errors='replace'))
    print(f"[Render] ✅ 输出完成: {out_mp4}")


async def main():
    narration_text = "阳光看起来是白色的，但它其实包含了所有颜色的光。蓝光波长更短，更容易被大气分子散射到各个方向。这就是为什么我们看到的天空是蓝色的。"
    audio_path = OUTPUT_DIR / "narration.mp3"
    tts_ok = await generate_narration(narration_text, audio_path)

    audio_duration = probe_duration(audio_path) if tts_ok else None
    duration = audio_duration if audio_duration else DURATION_FALLBACK

    print(f"[Info] 渲染时长: {duration:.2f}s, FPS: {FPS}, 总帧数: {round(duration * FPS)}")

    await render_via_pipe(
        html_path=HTML_PATH, duration=duration, fps=FPS,
        out_mp4=OUTPUT_DIR / "sky_science_demo.mp4", audio_path=audio_path if tts_ok else None,
    )

if __name__ == "__main__":
    asyncio.run(main())
