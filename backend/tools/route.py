"""路线查询工具：地名解析用 Open-Meteo 地理编码，路线用 OSRM（都免费、不需要 API key）。

⚠️ 已知限制：OSRM 的公共演示服务器只跑「驾车」profile，
   传 cycling / walking 它也会按驾车算（实测三种距离时长完全一样）。
   所以骑行/步行的时间我们只能当成粗略参考，会在结果里标注出来。
   要准确的步行/公交路线，得换成高德地图之类的服务（需要申请免费 key）。
"""
import httpx

from tools.geo import geocode

OSRM_URL = "https://router.project-osrm.org/route/v1/{profile}/{coords}"

# 用户嘴里的说法 → OSRM 的 profile
MODE_MAP = {
    "driving": "driving",
    "car": "driving",
    "驾车": "driving",
    "开车": "driving",
    "cycling": "cycling",
    "bike": "cycling",
    "骑行": "cycling",
    "walking": "foot",
    "walk": "foot",
    "步行": "foot",
    "走路": "foot",
}

MODE_LABEL = {"driving": "驾车", "cycling": "骑行", "foot": "步行"}

# OSRM 的转向类型/方向是英文，翻译成中文，页面显示才「直观」
MANEUVER_TYPE_CN = {
    "depart": "出发",
    "arrive": "到达",
    "turn": "转弯",
    "continue": "继续直行",
    "new name": "继续直行",
    "merge": "汇入车流",
    "on ramp": "上匝道",
    "off ramp": "下匝道",
    "fork": "走岔路",
    "roundabout": "进入环岛",
    "rotary": "进入环岛",
    "roundabout turn": "环岛转弯",
    "end of road": "路到尽头",
    "notification": "注意",
}
MANEUVER_MODIFIER_CN = {
    "left": "左转",
    "right": "右转",
    "slight left": "稍向左",
    "slight right": "稍向右",
    "sharp left": "急左转",
    "sharp right": "急右转",
    "straight": "直行",
    "uturn": "掉头",
}


def _step_text(step: dict) -> str:
    """把 OSRM 的一步转向翻成人话，例如「稍向右 · 沿 G2 京沪高速 · 12.3 公里」。"""
    maneuver = step.get("maneuver") or {}
    modifier = MANEUVER_MODIFIER_CN.get(maneuver.get("modifier") or "")
    kind = MANEUVER_TYPE_CN.get(maneuver.get("type") or "", "继续")
    action = modifier or kind
    road = (step.get("name") or "").strip()
    distance_m = step.get("distance") or 0
    if distance_m >= 1000:
        dist = f"{distance_m / 1000:.1f} 公里"
    else:
        dist = f"{int(distance_m)} 米"
    parts = [action]
    if road:
        parts.append(f"沿 {road}")
    parts.append(dist)
    return " · ".join(parts)


def _thin(coords: list, limit: int = 400) -> list:
    """轨迹点太多（上千个）会让响应体很大，等间隔抽稀到 limit 个以内。"""
    n = len(coords)
    if n <= limit:
        return coords
    step = n / limit
    picked = [coords[int(i * step)] for i in range(limit)]
    if picked[-1] != coords[-1]:
        picked.append(coords[-1])  # 保证终点不丢
    return picked


TOOL_SPEC = {
    "type": "function",
    "name": "get_route",
    "description": (
        "查询两个城市/地点之间的路线，返回距离和预计耗时。"
        "当用户问怎么去、多远、要开多久、怎么走时使用。"
        "起点和终点都传中文地名（例如 北京、上海）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "起点地名，例如 北京"},
            "destination": {"type": "string", "description": "终点地名，例如 上海"},
            "mode": {
                "type": "string",
                "enum": ["driving", "cycling", "walking"],
                "description": "出行方式，默认 driving（驾车）",
            },
        },
        "required": ["origin", "destination"],
    },
}


def describe(origin: str, destination: str, mode: str = "driving") -> str:
    label = MODE_LABEL.get(MODE_MAP.get(mode, "driving"), "驾车")
    return f"正在规划「{origin} → {destination}」的{label}路线…"


async def run(
    origin: str, destination: str, mode: str = "driving", with_geometry: bool = False
) -> dict:
    """查路线。

    with_geometry=True 时额外返回路线轨迹和转向指引（给「路线」页面画地图用）。
    注意：这个参数【故意】没写进 TOOL_SPEC —— 轨迹上千个点，塞给模型又占token又没用。
    """
    profile = MODE_MAP.get(mode, "driving")
    label = MODE_LABEL.get(profile, "驾车")

    start = await geocode(origin)
    end = await geocode(destination)
    missing = [n for n, p in ((origin, start), (destination, end)) if not p]
    if missing:
        return {
            "error": f"没找到地名：{'、'.join(missing)}。请改用更常见的城市名（例如 北京、上海）。"
        }

    coords = f"{start['longitude']},{start['latitude']};{end['longitude']},{end['latitude']}"
    if with_geometry:
        params = {"overview": "full", "geometries": "geojson", "steps": "true"}
    else:
        params = {"overview": "false", "steps": "false"}

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(OSRM_URL.format(profile=profile, coords=coords), params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"查询路线失败：{exc}"}

    if data.get("code") != "Ok" or not data.get("routes"):
        return {"error": f"没算出路线（OSRM 返回 {data.get('code')}）"}

    route = data["routes"][0]
    distance_m = route.get("distance") or 0
    duration_s = route.get("duration") or 0

    result = {
        "起点": f"{start['name']}（{start.get('admin1') or ''}）",
        "终点": f"{end['name']}（{end.get('admin1') or ''}）",
        "出行方式": label,
        "总距离": f"{distance_m / 1000:.1f} 公里",
        "预计耗时": f"{int(duration_s // 3600)} 小时 {int(duration_s % 3600 // 60)} 分钟",
        "数据来源": "OSRM",
    }

    if with_geometry:
        # 轨迹：[[经度, 纬度], ...]，WGS-84 坐标（页面画地图时用）
        geometry = (route.get("geometry") or {}).get("coordinates") or []
        if geometry:
            result["轨迹"] = _thin(geometry)
        # 转向指引
        steps = []
        for leg in route.get("legs") or []:
            for step in leg.get("steps") or []:
                steps.append(_step_text(step))
        if steps:
            result["转向指引"] = steps
        result["起终点坐标"] = {
            "起点": [start["longitude"], start["latitude"]],
            "终点": [end["longitude"], end["latitude"]],
        }

    if profile != "driving":
        result["注意"] = (
            "免费的 OSRM 演示服务器只提供驾车路线，"
            f"这里的「{label}」耗时其实是按驾车估算的，只能当粗略参考。"
        )

    return result
