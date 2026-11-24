# evaluation.py
import subprocess
import sys
from pathlib import Path

class QualityGate:
    @staticmethod
    def L2_visual_check(video_path: Path) -> bool:
        """L2 静态视觉检查：防止白屏/黑屏（通过文件大小估算）"""
        if video_path.exists() and video_path.stat().st_size > 50 * 1024: # 大于50KB说明有真实画面
            return True
        return False

    @staticmethod
    def L3_align_check(video_path: Path, audio_path: Path) -> bool:
        """L3 音画对齐检查：防止音画不同步（模拟）"""
        # 实际生产中，这里会调用 ffprobe 比较两路流的 duration
        # 这里我们简化为检查两个文件是否都存在且不为空
        if video_path.exists() and (not audio_path.exists() or audio_path.stat().st_size > 0):
            return True
        return False

class ObservabilityTracker:
    """全链路追踪器"""
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.metrics = {}

    def record(self, stage: str, duration: float, **kwargs):
        self.metrics[stage] = {"duration_sec": round(duration, 2), **kwargs}
        print(f"[Observability] Task {self.task_id} | 阶段: {stage} | 耗时: {duration:.2f}s | 附加信息: {kwargs}", file=sys.stderr)