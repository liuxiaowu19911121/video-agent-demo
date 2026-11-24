import asyncio
import subprocess
import sys
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from edge_tts import Communicate
from playwright.async_api import async_playwright

# 引入自定义模块
from models import VideoScript
from planner_agent import generate_script_by_llm

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    import shutil
    FFMPEG_EXE = shutil.which("ffmpeg") or "ffmpeg"

BASE_DIR = Path(__file__).parent.resolve()
SCIENCE_DIR = BASE_DIR / "science-demo"
OUTPUT_DIR = BASE_DIR / "renders"
OUTPUT_DIR.mkdir(exist_ok=True)

WIDTH, HEIGHT = 1920, 1080
FPS = 24

async def generate_narration(text: str, out_path: Path, timeout: float = 30.0) -> bool:
    try:
        communicate = Communicate(text, voice="zh-CN-XiaoxiaoNeural")
        await asyncio.wait_for(communicate.save(str(out_path)), timeout=timeout)
        return True
    except Exception as e:
        print(f"[TTS] 失败: {e}", file=sys.stderr)
        return False

def probe_duration(media_path: Path) -> float | None:
    if not media_path.exists(): return None
    cmd = [FFMPEG_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return None

async def render_via_pipe(html_path: Path, duration: float, fps: int, out_mp4: Path, audio_path: Path | None = None):
    total_frames = round(duration * fps)

    ffmpeg_cmd = [
        FFMPEG_EXE, "-y", "-probesize", "20M", "-analyzeduration", "20M",
        "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
    ]
    if audio_path and audio_path.exists():
        ffmpeg_cmd += ["-f", "mp3", "-i", str(audio_path)]

    ffmpeg_cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if audio_path and audio_path.exists():
        ffmpeg_cmd += ["-c:a", "aac", "-shortest"]
    ffmpeg_cmd += ["-movflags", "+faststart", str(out_mp4)]

    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--headless=new", "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu", "--disable-images",
            "--font-render-hinting=none", "--js-flags=--max-old-space-size=256",
        ])
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        await page.goto("file://" + str(html_path.resolve()), wait_until="domcontentloaded")

        is_ready = False
        for _ in range(50):
            is_ready = await page.evaluate("() => typeof window.__seekFrame === 'function' && !!window.__timelines")
            if is_ready: break
            await asyncio.sleep(0.1)

        if not is_ready:
            raise RuntimeError("❌ 等待超时：window.__seekFrame 未挂载。")

        print("[Playwright] 🎉 GSAP 就绪！开始逐帧渲染...")
        for i in range(total_frames):
            if ffmpeg_proc.poll() is not None:
                raise RuntimeError(f"❌ FFmpeg 提前退出！")
            t = i / fps
            await page.evaluate("(time) => window.__seekFrame(time)", t)
            await page.evaluate("() => new Promise(requestAnimationFrame)")
            frame_bytes = await page.screenshot(type="jpeg", quality=85, clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
            try:
                ffmpeg_proc.stdin.write(frame_bytes)
            except BrokenPipeError:
                raise RuntimeError(f"❌ 管道破裂！")
            if i % 24 == 0:
                print(f"  -> 已渲染 {i}/{total_frames} 帧...")
        await browser.close()

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    if ffmpeg_proc.returncode != 0:
        raise RuntimeError("FFmpeg 编码失败")
    print(f"[Render] ✅ 输出完成: {out_mp4}")


async def main():
    print("=== 视频生成 Agent 基础设施 阶段二 ===")
    topic = "为什么天空是蓝色"
    
    # 🧠 1. 唤起 Planner Agent 生成结构化数据
    raw_json_data = generate_script_by_llm(topic)

    # 🛡️ 2. L1 质量门禁：Pydantic 静态校验（防幻觉拦截）
    try:
        script_model = VideoScript(**raw_json_data)
        print("[L1 门禁] ✅ 大模型数据校验通过！")
    except Exception as e:
        print(f"[L1 门禁] ❌ 校验失败，拦截渲染:\n{e}")
        return

    # 🎵 3. 提取文本生成旁白

    # 修改后（增加正则清洗）：
    def strip_html(text: str) -> str:
        """清洗 HTML 标签，只保留纯文本"""
        return re.sub(r'<[^>]+>', '', text)

    narration_text = "".join([f"{strip_html(s.title)}。{strip_html(s.text)}。" for s in script_model.scenes])
    audio_path = OUTPUT_DIR / "narration.mp3"
    tts_ok = await generate_narration(narration_text, audio_path)

    # 🎬 4. 时间轴自适应（高级特性）
    # 获取真实音频时长
    real_audio_dur = probe_duration(audio_path) if tts_ok else None
    
    if real_audio_dur:
        # 计算大模型给的预期总时长
        expected_dur = sum([s.duration for s in script_model.scenes])
        # 计算缩放比例 (真实音频 / 预期时长)
        scale_factor = real_audio_dur / expected_dur
        
        # 按比例动态调整每个场景的时长
        for scene in script_model.scenes:
            scene.duration = round(scene.duration * scale_factor, 2)
            
        print(f"[TimeAlign] 真实音频时长 {real_audio_dur:.2f}s，预期时长 {expected_dur:.2f}s，缩放比例 {scale_factor:.2f}")
        final_duration = real_audio_dur
    else:
        final_duration = sum([s.duration for s in script_model.scenes])

    # 🖥️ 5. Jinja2 渲染 HTML
    env = Environment(loader=FileSystemLoader(str(SCIENCE_DIR)))
    template = env.get_template('template.html')
    
    render_context = {
        "video_title": script_model.video_title,
        "duration": final_duration,
        "scene_1": script_model.scenes[0].model_dump(),
        "scene_2": script_model.scenes[1].model_dump(),
        "scene_3": script_model.scenes[2].model_dump(),
        "chart_data": [c.model_dump() for c in script_model.chart_data]
    }
    
    rendered_html = template.render(**render_context)
    rendered_html_path = SCIENCE_DIR / "index.html"
    with open(rendered_html_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    print(f"[Info] 最终渲染时长: {final_duration:.2f}s")

    # 🚀 6. 送入管道渲染
    await render_via_pipe(
        html_path=rendered_html_path, duration=final_duration, fps=FPS,
        out_mp4=OUTPUT_DIR / "sky_science_demo_v2.mp4", audio_path=audio_path if tts_ok else None,
    )

if __name__ == "__main__":
    asyncio.run(main())