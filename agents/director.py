# agents/director.py
import json
from models import DirectorScript

def generate_script(topic: str) -> DirectorScript:
    print(f"[Director] 正在规划主题: {topic}")
    # 实际开发中替换为大模型 API (如 Qwen/DeepSeek)，使用 JSON mode
    mock_json = """
    {
      "title": "拔火罐为什么能吸住肉？",
      "scenes": [
        {"id": 1, "duration": 4, "text": "火一烧，罐里的气变少。", "visual_intent": "火焰燃烧，气压下降，皮肤形变"},
        {"id": 2, "duration": 5, "text": "外部大气压把皮肤压进罐里。", "visual_intent": "未知的复杂医学动画"}
      ]
    }
    """
    return DirectorScript(**json.loads(mock_json))