"""天气查询工具：数据来自 Open-Meteo（免费、不需要 API key）。

给 AI 用的「工具」要提供三样东西：
  TOOL_SPEC  —— 给模型看的说明书（名字、用途、参数结构），模型据此决定要不要调、传什么参数
  describe() —— 给用户看的进度提示（前端会显示成「🔧 正在查询…」）
  run()      —— 真正干活的函数，返回结果会被回传给模型
"""
import httpx

from tools.geo import geocode

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO 天气代码 → 中文说明
WMO_CODES = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴小冰雹",
    99: "雷阵雨伴大冰雹",
}

TOOL_SPEC = {
    "type": "function",
    "name": "get_weather",
    "description": (
        "查询某个城市当前的天气和未来几天的预报。"
        "当用户问天气、气温、下不下雨、要不要带伞、穿什么衣服、适不适合出门时使用。"
        "地名请传中文城市名（例如 北京、上海、广州）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称，例如 北京"},
            "days": {
                "type": "integer",
                "description": "要预报几天（1-7），用户只问今天/现在就用 1",
            },
        },
        "required": ["city"],
    },
}


def describe(city: str, days: int = 1) -> str:
    return f"正在查询「{city}」的天气…"


async def run(city: str, days: int = 1) -> dict:
    place = await geocode(city)
    if not place:
        return {
            "error": f"没找到地名「{city}」。请改用更常见的城市名（例如 北京、上海、广州）。"
        }

    try:
        days = max(1, min(int(days or 1), 7))
    except (TypeError, ValueError):
        days = 1

    params = {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": days,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"查询天气失败：{exc}"}

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    dates = daily.get("time") or []

    forecast = []
    for i, day in enumerate(dates):
        forecast.append(
            {
                "日期": day,
                "天气": WMO_CODES.get((daily.get("weather_code") or [None])[i], "未知"),
                "最高温": (daily.get("temperature_2m_max") or [None])[i],
                "最低温": (daily.get("temperature_2m_min") or [None])[i],
                "降水概率": f"{(daily.get('precipitation_probability_max') or [None])[i]}%",
            }
        )

    # 地点标签：省和国家拼起来时加个「·」分隔，否则会显示成「湖南中国」
    region = "·".join(p for p in (place.get("admin1"), place.get("country")) if p)

    return {
        "地点": f"{place['name']}（{region}）",
        "当前": {
            "天气": WMO_CODES.get(cur.get("weather_code"), "未知"),
            "温度": f"{cur.get('temperature_2m')}℃",
            "体感温度": f"{cur.get('apparent_temperature')}℃",
            "湿度": f"{cur.get('relative_humidity_2m')}%",
            "风速": f"{cur.get('wind_speed_10m')} km/h",
            "观测时间": cur.get("time"),
        },
        "预报": forecast,
        "数据来源": "Open-Meteo",
    }
