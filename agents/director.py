# agents/director.py
import json
import os
from openai import OpenAI
from models import DirectorScript

# 初始化 DeepSeek 客户端（兼容 OpenAI SDK）
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 将 Pydantic Schema 转为 Prompt 中的格式说明
DIRECTOR_SYSTEM_PROMPT = """你是一个专业的科普视频导演。你的任务是将用户给定的科普主题，拆解成结构化的分镜剧本。

你必须输出一个严格的 JSON 对象，格式如下（不要输出任何 Markdown 标记或额外解释）：
{
  "title": "视频总标题",
  "scenes": [
    {
      "id": 1,
      "duration": 4.0,
      "text": "该场景的旁白文案",
      "visual_intent": "视觉意图描述，用于组件路由匹配",
      "emotion": "情感基调，可选：mysterious, intense, calm, neutral",
      "pacing": "节奏，可选：slow, fast, normal"
    }
  ]
}

要求：
- 分镜数量控制在 3~5 个。
- 每个 scene 的 duration 在 3~6 秒之间。
- emotion 和 pacing 必须从给定的可选值中选择，用以体现视频的节奏起伏。
- visual_intent 要简洁概括该场景需要展示的视觉元素（如"拔火罐"、"气压变化"、"血管剖面"）。
"""

def generate_script(topic: str) -> DirectorScript:
    print(f"[Director] 正在调用 DeepSeek-V4-Flash 规划主题: {topic}")
    
    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"科普主题：{topic}"}
        ],
        response_format={"type": "json_object"},  # 开启 JSON Mode
        temperature=1.0,  # DeepSeek 官方推荐值[reference:5]
        max_tokens=2000,
        extra_body={"thinking": {"type": "disabled"}}
        #enable_thinking=False  # 剧本生成不需要深度思考，关闭以提速降本
    )
    
    raw_json = json.loads(response.choices[0].message.content)

    print(json.dumps(raw_json, ensure_ascii=False, indent=2))
    # 用 Pydantic 做二次校验，拦截 LLM 可能产生的字段缺失/类型错误
    try:
        script = DirectorScript(**raw_json)
    except Exception as e:
        print(f"[Director] ❌ LLM 输出不符合 Schema: {e}")
        raise RuntimeError(f"Director Agent 输出校验失败: {e}")
    
    print(f"[Director] ✅ 剧本生成完成，共 {len(script.scenes)} 个分镜")
    return script