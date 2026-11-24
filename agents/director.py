# agents/director.py
import json
from models import DirectorScript

def generate_script(topic: str) -> DirectorScript:
    print(f"[Director] 正在规划主题: {topic}")
    # 模拟大模型输出：注意 emotion 和 pacing 的变化
    mock_json = """
    {
      "title": "拔火罐为什么能吸住肉？",
      "scenes": [
        {
          "id": 1, 
          "duration": 4.0, 
          "text": "火一烧，罐里的气慢慢变少...", 
          "visual_intent": "拔火罐", 
          "emotion": "mysterious", 
          "pacing": "slow"
        },
        {
          "id": 2, 
          "duration": 5.0, 
          "text": "砰！外部大气压瞬间把皮肤死死压进罐里！", 
          "visual_intent": "拔火罐", 
          "emotion": "intense", 
          "pacing": "fast"
        }
      ]
    }
    """
    return DirectorScript(**json.loads(mock_json))