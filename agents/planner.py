# agents/planner.py
import json
import os
import asyncio
from openai import OpenAI
from models import (
    DirectorScript, RenderTree, SceneIntent,
    CuppingComponent, CuppingComponentParams,
    TextComponent, TextComponentParams
)
from agents.coder import background_coder_reviewer_loop

client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ============ 组件工具定义（Function Calling Schema） ============
COMPONENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "use_cupping_scene",
            "description": "拔火罐物理动画组件。包含火焰燃烧、负压数值显示、皮肤形变。适合解释气压变化、拔火罐原理等场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "底部字幕文案"},
                    "pressure": {"type": "integer", "description": "罐内负压数值，负数，如 -29"},
                    "show_flame": {"type": "boolean", "description": "是否显示火焰动画"},
                    "variant": {
                        "type": "string",
                        "enum": ["slow_burn", "fast_snap", "normal"],
                        "description": "动画变体。slow_burn=缓慢拉伸(悬疑感)，fast_snap=瞬间弹射(冲击力)，normal=默认"
                    }
                },
                "required": ["text", "pressure", "show_flame", "variant"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "use_text_scene",
            "description": "纯文字展示组件。当没有合适的视觉组件，或需要过渡/总结时，使用此组件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "居中显示的核心文案"}
                },
                "required": ["text"]
            }
        }
    }
]

PLANNER_SYSTEM_PROMPT = """你是一个视频制片人。你的任务是根据给定的分镜意图、文案、情感和节奏，从工具库中选择最合适的视觉组件，并填充参数。

规则：
1. 优先匹配 visual_intent 与工具描述中的关键词。如果没有匹配的视觉组件，必须降级使用 use_text_scene。
2. 根据 pacing 和 emotion 选择 cupping 组件的 variant：
   - pacing=slow 且 emotion=mysterious → slow_burn
   - pacing=fast 且 emotion=intense → fast_snap
   - 其他情况 → normal
3. 每个分镜只调用一个工具。
"""

def _plan_one_scene(scene: SceneIntent) -> tuple:
    """对单个 Scene 调用 LLM 做组件路由，返回 (component_type, params_dict)"""
    user_content = (
        f"分镜编号：{scene.id}\n"
        f"文案：{scene.text}\n"
        f"视觉意图：{scene.visual_intent}\n"
        f"情感：{scene.emotion}\n"
        f"节奏：{scene.pacing}\n"
        f"时长：{scene.duration}s"
    )
    
    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        tools=COMPONENT_TOOLS,
        tool_choice="auto",  # 让模型自主选择工具，但不强制
        temperature=0.3,     # 路由任务需要确定性，温度调低
        extra_body={"thinking": {"type": "disabled"}}
        #enable_thinking=False
    )
    
    message = response.choices[0].message
    
    if not message.tool_calls:
        # LLM 没有调用任何工具 → 安全降级为纯文字
        print(f"  -> Scene {scene.id} 未匹配组件，降级为 [text]")
        return "text", {"text": scene.text}
    
    tool_call = message.tool_calls[0]
    tool_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    
    if tool_name == "use_cupping_scene":
        return "cupping", args
    else:
        return "text", args


def plan_render_tree(script: DirectorScript) -> RenderTree:
    print("[Planner] 正在调用 DeepSeek-V4-Flash 进行组件路由...")
    scenes = []
    
    for scene in script.scenes:
        comp_type, params_dict = _plan_one_scene(scene)
        
        if comp_type == "cupping":
            print(f"  -> Scene {scene.id} 命中 [cupping] 组件，variant={params_dict.get('variant')}")
            comp = CuppingComponent(
                duration=scene.duration,
                params=CuppingComponentParams(**params_dict)
            )
            scenes.append(comp)
        else:
            print(f"  -> Scene {scene.id} 降级为 [text] 组件，触发后台进化")
            comp = TextComponent(
                duration=scene.duration,
                params=TextComponentParams(**params_dict)
            )
            scenes.append(comp)
            # 异步触发后台 Coder-Reviewer，不阻塞主流程
            asyncio.create_task(background_coder_reviewer_loop(scene.visual_intent))
    
    print(f"[Planner] ✅ 路由完成，共 {len(scenes)} 个场景")
    return RenderTree(title=script.title, scenes=scenes)