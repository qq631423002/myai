"""地名 → 经纬度。

用 Open-Meteo 的地理编码接口：免费、不需要注册 key、支持中文城市名。
（注意它是「城市/地区」级搜索，"北京大学"这种具体地点搜不到。）

⚠️ 这个文件里全是踩过的坑，别随便简化。接口底层是 GeoNames，实测有四个坑：

坑 1：中文地级市登记的名字常带「市」字。
      搜「湘潭」时**湖南省湘潭市根本不在结果里**，只返回两个同名村子
      （安徽一个、云南一个，都是村级、没有人口数据）。
      直接取 results[0] 就会把安徽那个村子当成湘潭 —— 天气显示安徽。
      「长沙」同样：搜「长沙」只返回重庆/贵州/广东的几个村，得搜「长沙市」。

坑 2：用户爱带省份一起输（「湖南湘潭」），但接口这么搜直接返回 0 条。

坑 3：外国城市的简体中文名常常对不上库里的标签。
      东京在库里的中文名是繁体「東京」，搜「东京」只命中江苏/浙江的村子；
      「伦敦」同理对不上英国的「倫敦」。所以要有一张别名表。

坑 4：**不能只看「名字一模一样」**。
      搜 Vancouver 时，美国华盛顿州那个 19 万人的小城名字跟输入完全一致，
      而加拿大温哥华在库里的名字是繁体「溫哥華」。只看名字就会挑错国家。

所以流程是：多套搜索词全收齐 → 去重 → 统一打分排序。
"""
import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# 名字匹配加分。故意给得比「行政级别 + 人口」轻（坑 4）：
# 名字完全一致但只是个小村镇时，不该压过真正的大城市。
_NAME_EXACT = 30
_NAME_PREFIX = 20

# 行政区级别加分。GeoNames 的 feature_code 含义：
#   PPLC=首都, PPLA=省级首府, PPLA2=地级市, PPLA3=县级市, PPLA4=区, PPL=普通村镇
# 分值也不宜过大：温哥华（加拿大）在库里被标成 PPL，
# 而美国那个同名的却是 PPLA2，级别加分一重就会挑错。
_ADMIN_BONUS = {"PPLC": 25, "PPLA": 20, "PPLA2": 18, "PPLA3": 14, "PPLA4": 8}

# 人口加分：按「本次结果里人口最多的那条」做归一化，最多加 60 分。
# 用相对值而不是绝对值，是因为同名时我们只需要知道「谁更大」。
_POP_WEIGHT = 60

# 已经找到一个「明摆着就是它」的大城市了吗？够好就不用再试别的搜索词了。
# 这个判断故意只用绝对指标（行政级别 + 人口），不看打分 ——
# 否则小结果集里「矮子里拔将军」会让一个村子显得很高分，导致过早收手（坑 1、3）。
_EXCELLENT_CODES = ("PPLC", "PPLA", "PPLA2", "PPLA3")
_EXCELLENT_POP = 300_000

# 已经是行政后缀结尾的名字，就不用再补「市」了
_ADMIN_SUFFIXES = ("市", "县", "区", "省", "州", "盟", "旗")

# 中文里常见的省级前缀：用户爱输「湖南湘潭」「广东深圳」，但接口只认市名本身。
# 注意：接口没法用省份过滤，这里只是把它剥掉再搜，并不是「限定在该省」。
_PROVINCE_PREFIXES = (
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建",
    "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州",
    "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
)

# 坑 3 的补丁：简体中文名搜不到的外国城市，改用它本地的名字去搜。
# 只在这批中文搜索词都搜不出大城市时才会用到，平时不影响国内城市。
# 加新条目请顺手跑一遍测试，确认命中是对的（比如「纽约」得用 New York City，
# 直接搜 New York 会命中美国内布拉斯加那个叫「约克」的小镇）。
_ALIASES = {
    "东京": "Tokyo", "大阪": "Osaka", "京都": "Kyoto", "札幌": "Sapporo",
    "名古屋": "Nagoya", "首尔": "Seoul", "釜山": "Busan",
    "新加坡": "Singapore", "曼谷": "Bangkok", "吉隆坡": "Kuala Lumpur",
    "雅加达": "Jakarta", "马尼拉": "Manila", "河内": "Hanoi",
    "迪拜": "Dubai", "孟买": "Mumbai", "新德里": "New Delhi",
    "伦敦": "London", "巴黎": "Paris", "柏林": "Berlin", "罗马": "Rome",
    "马德里": "Madrid", "莫斯科": "Moscow", "阿姆斯特丹": "Amsterdam",
    "纽约": "New York City", "洛杉矶": "Los Angeles", "旧金山": "San Francisco",
    "芝加哥": "Chicago", "西雅图": "Seattle", "波士顿": "Boston",
    "温哥华": "Vancouver", "多伦多": "Toronto", "悉尼": "Sydney",
    "墨尔本": "Melbourne", "奥克兰": "Auckland", "开罗": "Cairo",
    "伊斯坦布尔": "Istanbul", "圣保罗": "Sao Paulo", "墨西哥城": "Mexico City",
    "台北": "Taipei", "高雄": "Kaohsiung",
}


def _score(hit: dict, query: str, max_pop: int) -> float:
    """给一条候选打分，分数越高越像用户想找的那个地方。

    三部分：名字像不像（轻）+ 行政级别（中）+ 人口（相对值，重）。
    """
    score = 0.0
    name = hit.get("name") or ""

    if name == query:
        score += _NAME_EXACT
    # 「湘潭」命中「湘潭市」：只差一个行政后缀，也算高度匹配
    elif name.startswith(query) or query.startswith(name):
        score += _NAME_PREFIX

    score += _ADMIN_BONUS.get(hit.get("feature_code") or "", 0)

    if max_pop:
        score += _POP_WEIGHT * (hit.get("population") or 0) / max_pop

    return score


def _excellent(hits: list) -> bool:
    """结果里有没有一条「明摆着就是它」的大城市？"""
    return any(
        h.get("feature_code") in _EXCELLENT_CODES
        and (h.get("population") or 0) >= _EXCELLENT_POP
        for h in hits
    )


def _populated(hits: list) -> list:
    """只保留「有居民点」的候选。

    岛屿、山峰、湖泊、机场、公园的名字可能跟城市很像，
    人口字段甚至更大 —— 搜温哥华会冒出一个 74.8 万人的 Vancouver Island，
    拿它的坐标去查天气就成了海岛天气。所以先按 feature_code 过滤掉非居民点。
    如果一条 PPL* 都没有（香港、新加坡在库里是别的类型），就退回用全部候选。
    """
    people = [h for h in hits if (h.get("feature_code") or "").startswith("PPL")]
    return people or hits


def _strip_province(name: str) -> str | None:
    """「湖南湘潭」→「湘潭」。剥不掉就返回 None。"""
    for prefix in _PROVINCE_PREFIXES:
        rest = name[len(prefix):]
        # 剩下的至少 2 个字才算有效（否则「吉林」会被剥成空、「北京」同理）
        if name.startswith(prefix) and len(rest) >= 2:
            return rest
    return None


def _variants(query: str) -> list:
    """列出要试的搜索词，按优先级排序。

    带省名时先试剥掉省名的形式（「广东深圳」→ 深圳），
    因为省份对接口来说只是干扰；每个形式再补一个「市」的版本。
    """
    stripped = _strip_province(query)
    bases = [stripped, query] if stripped else [query]

    result = []
    for base in bases:
        for candidate in (base, None if base.endswith(_ADMIN_SUFFIXES) else base + "市"):
            if candidate and candidate not in result:
                result.append(candidate)
    return result


async def _search(client: httpx.AsyncClient, name: str) -> list:
    resp = await client.get(
        GEOCODE_URL,
        params={"name": name, "count": 10, "language": "zh", "format": "json"},
    )
    resp.raise_for_status()
    return resp.json().get("results") or []


async def _collect(query: str) -> list:
    """把所有搜索词的结果收齐。网络异常会往上抛，由 geocode 决定重试。"""
    async with httpx.AsyncClient(timeout=15) as client:
        hits: list = []

        # 1) 多套搜索词逐个试，一出现「明摆着的大城市」就收手
        for variant in _variants(query):
            hits += await _search(client, variant)
            if _excellent(hits):
                break

        # 2) 别名无条件查一次（有别名时）。不能因为中文搜索「看起来还行」就跳过：
        #    搜「奥克兰」会命中美国加州那个 41.9 万人的城市，
        #    看起来完全够格，但用户要的是新西兰奥克兰 ——
        #    结果一起排序再比大小，才是对的。
        alias = _ALIASES.get(query) or _ALIASES.get(_strip_province(query) or "")
        if alias:
            hits += await _search(client, alias)

        return hits


async def geocode(name: str) -> dict | None:
    """把地名换成坐标。找不到就返回 None。"""
    query = (name or "").strip()
    if not query:
        return None

    hits: list = []
    for attempt in (0, 1):
        try:
            hits = await _collect(query)
            break
        except Exception:  # noqa: BLE001
            # 网络抖一下就重试一次；两次都失败就当作「查不到」，
            # 由调用方给用户明确提示（宁可不给，也不要给错的地方）
            if attempt == 1:
                return None

    # 同一条可能被搜到多次，按坐标去重
    seen, unique = set(), []
    for hit in hits:
        key = (hit.get("latitude"), hit.get("longitude"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)

    if not unique:
        return None

    candidates = _populated(unique)
    max_pop = max((h.get("population") or 0) for h in candidates)
    best = max(candidates, key=lambda h: _score(h, query, max_pop))
    return {
        "name": best.get("name"),
        "latitude": best.get("latitude"),
        "longitude": best.get("longitude"),
        "admin1": best.get("admin1"),   # 省/州
        "country": best.get("country"),
    }
