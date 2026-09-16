"""给前端「页面」直接调用的普通接口（不经过大模型）。

天气页 / 路线页用这两个接口拿数据 —— 和 AI 的工具调用**共用 tools/ 里同一份实现**，
所以天气/路线的逻辑只写了一遍，两边都受益。

（另：AI 那边的工具接口在 routers/chat.py，走 SSE 流式。）
"""
from fastapi import APIRouter, HTTPException, Query

from tools import route as route_tool
from tools import weather as weather_tool

router = APIRouter(tags=["features"])


@router.get("/api/weather")
async def get_weather(
    city: str = Query(..., description="城市名，例如 北京"),
    days: int = Query(3, ge=1, le=7, description="预报天数 1-7"),
):
    """天气页用：某个城市的实时天气 + 未来几天预报。"""
    result = await weather_tool.run(city=city, days=days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/api/route")
async def get_route(
    origin: str = Query(..., description="起点，例如 北京"),
    destination: str = Query(..., description="终点，例如 上海"),
    mode: str = Query("driving", description="driving(驾车) / cycling(骑行) / walking(步行)"),
):
    """路线页用：距离、耗时、地图轨迹、转向指引。

    这里的 with_geometry=True 只给页面用；AI 调工具时拿的是精简版（不含上千个轨迹点）。
    """
    result = await route_tool.run(
        origin=origin, destination=destination, mode=mode, with_geometry=True
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
