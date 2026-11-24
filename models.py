# models.py
from pydantic import BaseModel, Field
from typing import List, Literal, Union
from typing_extensions import Annotated

# --- 第一层 Director 的产出 ---
class SceneIntent(BaseModel):
    id: int
    duration: float
    text: str = Field(description="旁白文案")
    visual_intent: str = Field(description="视觉意图描述")
    emotion: str = Field(default="neutral", description="情感基调，如 mysterious, intense, calm")
    pacing: str = Field(default="normal", description="节奏，如 slow, fast, normal")

class DirectorScript(BaseModel):
    title: str
    scenes: List[SceneIntent]

# --- 第二层 Planner 的产出 (组件 DSL) ---
class TextComponentParams(BaseModel):
    text: str

class CuppingComponentParams(BaseModel):
    text: str
    pressure: int
    show_flame: bool
    variant: str = Field(default="normal", description="动画变体：slow_burn, fast_snap, normal")

class TextComponent(BaseModel):
    type: Literal["text"] = "text"
    duration: float
    params: TextComponentParams

class CuppingComponent(BaseModel):
    type: Literal["cupping"] = "cupping"
    duration: float
    params: CuppingComponentParams

# 组合成最终的渲染树
class RenderTree(BaseModel):
    title: str
    scenes: List[Annotated[Union[CuppingComponent, TextComponent], Field(discriminator='type')]]