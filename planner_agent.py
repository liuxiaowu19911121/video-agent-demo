# planner_agent.py
import json
import sys  # 新增导入
from models import VideoScript

def generate_script_by_llm(topic: str) -> dict:
    """
    模拟大模型（Planner Agent）根据主题生成分镜 JSON。
    未来这里会变成 requests.post("https://api.openai.com/...")
    """
    # 关键修改：file=sys.stderr
    print(f"[Planner Agent] 正在思考主题: {topic} ...", file=sys.stderr) 
    
    # 模拟 LLM 输出的 JSON 数据
    mock_json_str = """
    {
      "video_title": "为什么天空是蓝色",
      "scenes": [
        {
          "title": "阳光看起来是白色的",
          "text": "但它其实包含了所有颜色的光。",
          "duration": 4.0
        },
        {
          "title": "蓝光波长更短",
          "text": "更容易被大气分子<span class=\\"highlight\\">散射</span>到各个方向。",
          "duration": 4.0
        },
        {
          "title": "不同颜色的散射强度",
          "text": "不同颜色的光，散射能力大不相同。",
          "duration": 4.0
        }
      ],
      "chart_data": [
        {"label": "红光", "value": 30},
        {"label": "绿光", "value": 55},
        {"label": "蓝光", "value": 100}
      ]
    }
    """
    return json.loads(mock_json_str)