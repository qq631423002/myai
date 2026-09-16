"""时间 / 时区工具：纯本地实现，不联网、不需要 API key。

能回答这几类问题：
  - 现在几点？今天几号、星期几？
  - 纽约 / 东京现在几点？
  - 北京时间下午 3 点是洛杉矶几点？
  - 两地时差多少？

时区名两种写法都认：IANA 名（Asia/Shanghai）和中文城市名（北京、纽约、洛杉矶）。

实现说明：用标准库 `zoneinfo`，夏令时是准的（实测纽约 9 月返回 EDT -0400）。
Windows 上 `zoneinfo` 依赖 IANA 时区数据库，万一报「时区不存在」就装一下 tzdata
（已写进 requirements.txt）：
    pip install tzdata
"""
from datetime import datetime, timedelta, timezone

TOOL_SPEC = {
    "type": "function",
    "name": "get_time",
    "description": (
        "查询当前时间，或者做跨时区时间换算。"
        "当用户问「现在几点」「今天几号/星期几」「纽约现在几点」"
        "「北京时间下午3点是洛杉矶几点」「两地时差多少」这类问题时使用。"
        "时区可以写城市名（北京、纽约、洛杉矶）或 IANA 名（Asia/Shanghai）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "要查询的时区或城市。不填就是本机所在时区（也可以填「本地」）",
            },
            "convert_time": {
                "type": "string",
                "description": (
                    "可选。要换算的具体时间，格式 YYYY-MM-DD HH:MM 或 HH:MM。"
                    "填了就表示做换算（而不是查当前时间）"
                ),
            },
            "from_timezone": {
                "type": "string",
                "description": "可选。convert_time 那个时间是按哪个时区写的，例如 北京",
            },
        },
        "required": [],
    },
}

# 中文（及常用外文）城市名 → IANA 时区名。模型很可能直接传中文城市名，所以必须有这层映射
CITY_TO_TZ = {
    "中国": "Asia/Shanghai",
    "北京": "Asia/Shanghai",
    "上海": "Asia/Shanghai",
    "广州": "Asia/Shanghai",
    "深圳": "Asia/Shanghai",
    "成都": "Asia/Shanghai",
    "香港": "Asia/Hong_Kong",
    "台北": "Asia/Taipei",
    "东京": "Asia/Tokyo",
    "日本": "Asia/Tokyo",
    "首尔": "Asia/Seoul",
    "韩国": "Asia/Seoul",
    "新加坡": "Asia/Singapore",
    "曼谷": "Asia/Bangkok",
    "泰国": "Asia/Bangkok",
    "新德里": "Asia/Kolkata",
    "印度": "Asia/Kolkata",
    "迪拜": "Asia/Dubai",
    "莫斯科": "Europe/Moscow",
    "俄罗斯": "Europe/Moscow",
    "伦敦": "Europe/London",
    "英国": "Europe/London",
    "巴黎": "Europe/Paris",
    "法国": "Europe/Paris",
    "柏林": "Europe/Berlin",
    "德国": "Europe/Berlin",
    "罗马": "Europe/Rome",
    "纽约": "America/New_York",
    "华盛顿": "America/New_York",
    "波士顿": "America/New_York",
    "芝加哥": "America/Chicago",
    "洛杉矶": "America/Los_Angeles",
    "旧金山": "America/Los_Angeles",
    "西雅图": "America/Los_Angeles",
    "多伦多": "America/Toronto",
    "温哥华": "America/Vancouver",
    "圣保罗": "America/Sao_Paulo",
    "悉尼": "Australia/Sydney",
    "澳大利亚": "Australia/Sydney",
    "墨尔本": "Australia/Melbourne",
    "奥克兰": "Pacific/Auckland",
    "开罗": "Africa/Cairo",
    "utc": "UTC",
    "格林威治": "UTC",
}

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

LOCAL_LABEL = "本机时区"


def _local_zone():
    """本机时区。astimezone() 拿到的就是带正确偏移和夏令时信息的时区对象。"""
    return datetime.now().astimezone().tzinfo or timezone.utc


def _resolve(name: str | None):
    """把时区名解析成 (tzinfo, 显示名, IANA 名)。认不出来返回 (None, 报错说明, None)。"""
    if not name or not str(name).strip():
        now = datetime.now().astimezone()
        return _local_zone(), LOCAL_LABEL, now.tzname() or "本地"

    raw = str(name).strip()
    key = raw.lower()

    if key in ("本地", "本机", "local", "here"):
        now = datetime.now().astimezone()
        return _local_zone(), LOCAL_LABEL, now.tzname() or "本地"

    # 中文城市名先过映射表（映射表里没有的，就当成 IANA 名直接试）
    iana = CITY_TO_TZ.get(raw) or CITY_TO_TZ.get(key) or raw

    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(iana), raw, iana
    except Exception:  # noqa: BLE001
        return (
            None,
            f"不认识的时区「{name}」。可以传城市名（北京、纽约、洛杉矶）"
            f"或 IANA 名（Asia/Shanghai、America/New_York）。",
            None,
        )


def _offset_text(dt: datetime) -> str:
    """把 UTC 偏移写成好看的「UTC+8」/「UTC-4:30」。"""
    offset = dt.utcoffset() or timedelta(0)
    total = int(offset.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    hours, minutes = divmod(abs(total), 60)
    return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


def _zone_text(label: str, iana: str | None, dt: datetime) -> str:
    """例如「纽约（America/New_York，UTC-4，夏令时）」或「本机时区（中国标准时间，UTC+8）」。"""
    dst = "，夏令时" if (dt.dst() and dt.dst() != timedelta(0)) else ""
    offset = _offset_text(dt)
    if label == LOCAL_LABEL:
        return f"{LOCAL_LABEL}（{iana or '本地'}，{offset}{dst}）"
    if iana and iana != label:
        return f"{label}（{iana}，{offset}{dst}）"
    return f"{iana or label}（{offset}{dst}）"


def describe(
    timezone: str = "本地", convert_time: str | None = None, from_timezone: str | None = None
) -> str:
    if convert_time and from_timezone:
        return f"正在把「{from_timezone} {convert_time}」换算成 {timezone} 的时间…"
    if timezone and str(timezone).strip() not in ("", "本地", "本机", "local"):
        return f"正在查询「{timezone}」的当前时间…"
    return "正在查询当前时间…"


def _parse_time(text: str) -> tuple[int, int, int, int, int] | None:
    """解析 'YYYY-MM-DD HH:MM' 或 'HH:MM'，返回 (年,月,日,时,分)。解析不出来返回 None。"""
    s = str(text).strip().replace("T", " ").replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%H:%M", "%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt.startswith("%H"):  # 只给了时间 → 补上「今天」
            today = datetime.now(_local_zone())
            return today.year, today.month, today.day, dt.hour, dt.minute
        return dt.year, dt.month, dt.day, dt.hour, dt.minute
    return None


async def run(
    timezone: str = "本地",
    convert_time: str | None = None,
    from_timezone: str | None = None,
) -> dict:
    target_tz, target_label, target_iana = _resolve(timezone)
    if target_tz is None:
        return {"error": target_label}

    # ---------- 情况一：跨时区换算 ----------
    if convert_time and from_timezone:
        source_tz, source_label, source_iana = _resolve(from_timezone)
        if source_tz is None:
            return {"error": source_label}

        parsed = _parse_time(convert_time)
        if not parsed:
            return {
                "error": f"时间格式看不懂：「{convert_time}」。请用 YYYY-MM-DD HH:MM 或 HH:MM 格式。"
            }
        year, month, day, hour, minute = parsed

        source_dt = datetime(year, month, day, hour, minute, tzinfo=source_tz)
        target_dt = source_dt.astimezone(target_tz)

        # 时差 = 同一时刻两个时区 UTC 偏移之差（夏令时已经算进去了）
        diff = (target_dt.utcoffset() or timedelta(0)) - (source_dt.utcoffset() or timedelta(0))
        diff_minutes = int(diff.total_seconds() // 60)
        amount = f"{abs(diff_minutes) / 60:g} 小时"
        if diff_minutes >= 0:
            diff_line = f"{target_label} 比 {source_label} 快 {amount}"
        else:
            diff_line = f"{target_label} 比 {source_label} 慢 {amount}"

        return {
            "原时间": f"{source_dt.strftime('%Y-%m-%d %H:%M')}（{_zone_text(source_label, source_iana, source_dt)}）",
            "换算结果": f"{target_dt.strftime('%Y-%m-%d %H:%M')}（{_zone_text(target_label, target_iana, target_dt)}）",
            "换算后的星期": WEEKDAY_CN[target_dt.weekday()],
            "时差": diff_line,
            "提示": "如果两边日期不同，注意是「昨天」还是「明天」",
        }

    # ---------- 情况二：查当前时间 ----------
    now = datetime.now(target_tz)
    return {
        "时区": _zone_text(target_label, target_iana, now),
        "日期": now.strftime("%Y-%m-%d"),
        "时间": now.strftime("%H:%M:%S"),
        "星期": WEEKDAY_CN[now.weekday()],
        "是否夏令时": "是" if (now.dst() and now.dst() != timedelta(0)) else "否",
    }
