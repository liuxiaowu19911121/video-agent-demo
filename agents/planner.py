# agents/planner.py
from models import DirectorScript, RenderTree, CuppingComponent, CuppingComponentParams, TextComponent, TextComponentParams
import asyncio
from agents.coder import background_coder_reviewer_loop

# 模拟 RAG 组件库
AVAILABLE_COMPONENTS = ["cupping"]

def plan_render_tree(script: DirectorScript) -> RenderTree:
    print("[Planner] 正在进行 RAG 路由匹配...")
    scenes = []
    
    for scene in script.scenes:
        # 简单的规则匹配：如果意图包含“火罐”或“气压”，则命中 cupping 组件
        if "气压" in scene.visual_intent or "皮肤" in scene.visual_intent:
            print(f"  -> Scene {scene.id} 命中 [cupping] 组件")
            comp = CuppingComponent(
                duration=scene.duration,
                params=CuppingComponentParams(text=scene.text, pressure=-29, show_flame=True)
            )
            scenes.append(comp)
        else:
            print(f"  -> Scene {scene.id} 未命中组件，降级为 [text] 组件，并触发后台 Coder")
            # 降级策略
            comp = TextComponent(
                duration=scene.duration,
                params=TextComponentParams(text=scene.text)
            )
            scenes.append(comp)
            
            # 触发后台异步自我进化 (不阻塞主流程)
            asyncio.create_task(background_coder_reviewer_loop(scene.visual_intent))
            
    return RenderTree(title=script.title, scenes=scenes)