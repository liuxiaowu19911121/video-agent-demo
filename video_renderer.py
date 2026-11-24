# video_renderer.py
import subprocess
import asyncio
import re
import time
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from edge_tts import Communicate
from playwright.async_api import async_playwright

from evaluation import QualityGate, ObservabilityTracker

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

def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)

def probe_duration(media_path: Path) -> float | None:
    if not media_path.exists(): return None
    cmd = [FFMPEG_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)]
    try:
        return float(subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip())
    except Exception:
        return None

async def generate_narration(text: str, out_path: Path) -> bool:
    try:
        communicate = Communicate(text, voice="zh-CN-XiaoxiaoNeural")
        await asyncio.wait_for(communicate.save(str(out_path)), timeout=30.0)
        return True
    except Exception:
        return False

async def render_via_pipe(html_path: Path, duration: float, out_mp4: Path, audio_path: Path, tracker: ObservabilityTracker):
    total_frames = round(duration * FPS)
    ffmpeg_cmd = [
        FFMPEG_EXE, "-y", "-probesize", "20M", "-analyzeduration", "20M",
        "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
    ]
    if audio_path.exists():
        ffmpeg_cmd += ["-f", "mp3", "-i", str(audio_path)]

    ffmpeg_cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if audio_path.exists():
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

        for _ in range(50):
            if await page.evaluate("() => typeof window.__seekFrame === 'function'"):
                break
            await asyncio.sleep(0.1)

        render_start = time.time()
        for i in range(total_frames):
            if ffmpeg_proc.poll() is not None:
                raise RuntimeError("FFmpeg 提前退出")
            t = i / FPS
            await page.evaluate("(time) => window.__seekFrame(time)", t)
            await page.evaluate("() => new Promise(requestAnimationFrame)")
            frame_bytes = await page.screenshot(type="jpeg", quality=85)
            ffmpeg_proc.stdin.write(frame_bytes)

        tracker.record("playwright_render", time.time() - render_start, frames=total_frames)
        await browser.close()

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    if ffmpeg_proc.returncode != 0:
        raise RuntimeError("FFmpeg 编码失败")

async def execute_full_pipeline(task_id: str, topic: str, task_db: dict, semaphore: asyncio.Semaphore):
    from planner_agent import generate_script_by_llm
    from models import VideoScript

    tracker = ObservabilityTracker(task_id)
    pipeline_start = time.time()

    async with semaphore:
        try:
            task_db[task_id]["status"] = "processing"
            
            # 1. LLM 生成 (L1 门禁)
            llm_start = time.time()
            raw_json = generate_script_by_llm(topic)
            script_model = VideoScript(**raw_json) # L1 校验
            tracker.record("llm_planning", time.time() - llm_start, tokens_mock=1500) # Mock Token成本

            # 2. TTS 生成
            tts_start = time.time()
            narration_text = "".join([f"{s.title}。{strip_html(s.text)}。" for s in script_model.scenes])
            audio_path = OUTPUT_DIR / f"{task_id}.mp3"
            await generate_narration(narration_text, audio_path)
            tracker.record("tts_generation", time.time() - tts_start)

            # 3. 时间轴计算
            real_audio_dur = probe_duration(audio_path)
            expected_dur = sum([s.duration for s in script_model.scenes])
            scale_factor = real_audio_dur / expected_dur if real_audio_dur else 1.0
            for scene in script_model.scenes:
                scene.duration = round(scene.duration * scale_factor, 2)
            final_duration = real_audio_dur or expected_dur

            # 4. 模板渲染
            env = Environment(loader=FileSystemLoader(str(SCIENCE_DIR)))
            template = env.get_template('template.html')
            render_context = {
                "video_title": script_model.video_title, "duration": final_duration,
                "scene_1": script_model.scenes[0].model_dump(), "scene_2": script_model.scenes[1].model_dump(),
                "scene_3": script_model.scenes[2].model_dump(), "chart_data": [c.model_dump() for c in script_model.chart_data]
            }
            rendered_html_path = SCIENCE_DIR / f"index_{task_id}.html"
            with open(rendered_html_path, "w", encoding="utf-8") as f:
                f.write(template.render(**render_context))

            # 5. 视频渲染
            out_mp4 = OUTPUT_DIR / f"{task_id}.mp4"
            await render_via_pipe(rendered_html_path, final_duration, out_mp4, audio_path, tracker)

            # 6. L2/L3 质量门禁
            gate_start = time.time()
            if not QualityGate.L2_visual_check(out_mp4):
                raise RuntimeError("L2 视觉检查失败：画面可能白屏")
            if not QualityGate.L3_align_check(out_mp4, audio_path):
                raise RuntimeError("L3 音画对齐检查失败")
            tracker.record("quality_gate", time.time() - gate_start)

            # 成功更新状态
            task_db[task_id]["status"] = "completed"
            task_db[task_id]["progress"] = 100
            task_db[task_id]["video_path"] = str(out_mp4)
            task_db[task_id]["metrics"] = tracker.metrics

        except Exception as e:
            print(f"[Error] Task {task_id} 失败: {e}", file=sys.stderr)
            task_db[task_id]["status"] = "failed"
            task_db[task_id]["error"] = str(e)
            
            # 🛡️ 兜底降级机制：绝不交白卷 (这里简单模拟，实际可用最简单的静态模板重新渲染)
            print(f"[Fallback] 触发兜底降级，生成静态占位视频...", file=sys.stderr)
            # ... 降级渲染逻辑(略) ...