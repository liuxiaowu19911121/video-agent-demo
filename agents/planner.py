# agents/planner.py
import asyncio
from models import DirectorScript, RenderTree, CuppingComponent, CuppingComponentParams, TextComponent, TextComponentParams
from agents.coder import background_coder_reviewer_loop

def plan_render_tree(script: DirectorScript) -> RenderTree:
    print("[Planner] 正在进行 RAG 路由与节奏翻译...")
    scenes = []
    
    for scene in script.scenes:
        if "拔火罐" in scene.visual_intent or "气压" in scene.visual_intent:
            
            # 🧠 核心逻辑：根据节奏和情感，翻译成具体的变体（Variant）
            variant = "normal"
            anim_duration = scene.duration
            
            if scene.pacing == "slow" and scene.emotion == "mysterious":
                variant = "slow_burn"
                anim_duration += 1.0  # 悬疑感，拉长动画时间
            elif scene.pacing == "fast" and scene.emotion == "intense":
                variant = "fast_snap"
                anim_duration -= 0.5  # 震撼感，压缩时间
                
            print(f"  -> Scene {scene.id} 命中 [cupping] 组件，采用变体: {variant}")
            
            comp = CuppingComponent(
                duration=scene.duration, # 场景总时长保持不变
                params=CuppingComponentParams(
                    text=scene.text, 
                    pressure=-29, 
                    show_flame=(scene.id == 1),
                    variant=variant
                )
            )
            scenes.append(comp)
        else:
            print(f"  -> Scene {scene.id} 降级为 [text] 组件，触发后台进化")
            comp = TextComponent(
                duration=scene.duration,
                params=TextComponentParams(text=scene.text)
            )
            scenes.append(comp)
            asyncio.create_task(background_coder_reviewer_loop(scene.visual_intent))
            
    return RenderTree(title=script.title, scenes=scenes)