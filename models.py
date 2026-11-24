# models.py
'''
from pydantic import BaseModel, Field
from typing import List

class SceneData(BaseModel):
    title: str = Field(description="场景主标题，简短有力")
    text: str = Field(description="场景正文，可以包含 HTML 标签如 <span>")
    duration: float = Field(description="该场景的预估时长（秒）")

class ChartItem(BaseModel):
    label: str = Field(description="图表的类别名称，例如'红光'")
    value: int = Field(ge=0, le=100, description="图表的数值，必须在 0-100 之间")

class VideoScript(BaseModel):
    video_title: str = Field(description="视频的标题")
    scenes: List[SceneData] = Field(description="分镜列表，目前固定为3个")
    chart_data: List[ChartItem] = Field(description="柱状图的数据，固定为3项")
'''

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