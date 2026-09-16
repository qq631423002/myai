"""海龟汤题库。

一道题包含两部分：
  汤面（surface）—— 讲给玩家听的、看似离谱的情境，前端可以拿到
  汤底（answer） —— 真相，**只在后端**，前端拿不到，玩家没法从请求里偷看

加新题就往 SOUPS 里加一条，其它代码都不用动。
"""
import random

SOUPS = [
    {
        "id": "water-and-gun",
        "title": "一杯水和一把枪",
        "difficulty": "简单",
        "tags": ["经典", "逻辑"],
        "surface": (
            "一个男人走进酒吧，对酒保说：“给我一杯水。”酒保没有倒水，"
            "反而从柜台下面掏出一把枪指着他。男人愣了一下，说：“谢谢。”然后转身走了。"
        ),
        "answer": (
            "男人打嗝停不下来，进酒吧是想讨杯水止嗝。酒保看出他在打嗝，于是掏枪吓他——"
            "受到惊吓能止嗝。男人被吓了一跳，嗝真的停了，所以道谢离开。"
        ),
    },
    {
        "id": "elevator-button",
        "title": "够不到的按钮",
        "difficulty": "简单",
        "tags": ["经典", "生活"],
        "surface": (
            "一个男人每天下班回家，坐电梯只按到 7 楼，然后走楼梯上 10 楼。"
            "可是一到下雨天，他会直接按 10 楼。"
        ),
        "answer": "他个子矮，只够得到 7 楼的按钮。下雨天他带了伞，可以用伞尖够到 10 楼的按钮。",
    },
    {
        "id": "two-fathers",
        "title": "两个父亲和两个儿子",
        "difficulty": "简单",
        "tags": ["经典", "脑筋急转弯"],
        "surface": (
            "两个父亲和两个儿子一起去钓鱼，一天下来只钓到 3 条鱼，"
            "但每个人都分到了整整 1 条。"
        ),
        "answer": "他们其实只有 3 个人——爷爷、爸爸、儿子。爷爷和爸爸是两个父亲，爸爸和儿子是两个儿子。",
    },
    {
        "id": "surgeon",
        "title": "手术室里的医生",
        "difficulty": "简单",
        "tags": ["经典", "思维定势"],
        "surface": (
            "一场车祸，父亲当场身亡，儿子被紧急送进手术室。"
            "外科医生看了一眼病人就说：“我不能给他做手术——他是我儿子。”"
            "可是孩子的父亲已经死了。"
        ),
        "answer": "外科医生是孩子的母亲。这道题考的是“医生一定是男性”的思维定势。",
    },
    {
        "id": "library-tears",
        "title": "借书人的眼泪",
        "difficulty": "简单",
        "tags": ["温情"],
        "surface": "一个男人走进图书馆，随手抽出一本书，翻开扉页看了几眼就红了眼眶，合上书默默放了回去。",
        "answer": "那本书是他已经去世的母亲（或妻子）写的，扉页上留着写给他的题词。",
    },
    {
        "id": "wrong-way",
        "title": "高速上的逆行",
        "difficulty": "中等",
        "tags": ["经典", "反转"],
        "surface": (
            "深夜，他独自开车在高速上。收音机里播报：“提醒司机朋友，前方路段有一辆车正在逆行。”"
            "他抬头看了看前方，脸色大变，猛地打方向盘撞向路边护栏。"
        ),
        "answer": (
            "他往前一看——迎面全是朝他开来的车灯。逆行的不是别人，是他自己："
            "他不知什么时候开上了对向车道。"
        ),
    },
    {
        "id": "wrong-room",
        "title": "半夜送毛巾",
        "difficulty": "中等",
        "tags": ["悬疑"],
        "surface": (
            "他出差住酒店，深夜有人敲门：“先生，您要的毛巾。”他隔着门说没叫毛巾。"
            "门外的人说：“不好意思，隔壁要的，送错了。”他松了口气，"
            "几秒后却脸色发白，立刻报警。"
        ),
        "answer": (
            "他住的是走廊最后一间房，隔壁根本没有房间（是墙）。“隔壁”不存在，"
            "说明门外的人在撒谎——他其实是在试探这个房间里有没有人。"
        ),
    },
    {
        "id": "desert-diver",
        "title": "沙漠里的潜水员",
        "difficulty": "中等",
        "tags": ["经典", "脑洞"],
        "surface": "在离海几百公里的沙漠深处，人们发现了一具尸体，穿着全套潜水服。",
        "answer": (
            "那片地方发生了森林大火，消防直升机到海里取水灭火，"
            "把正在浅海里潜水的他一并吸进了水箱，再连水一起洒在了火场上。"
        ),
    },
    {
        "id": "half-match",
        "title": "沙漠中的半根火柴",
        "difficulty": "中等",
        "tags": ["经典", "脑洞"],
        "surface": "沙漠中央躺着一个死人，手里紧紧攥着半根火柴。周围没有任何脚印，也没有任何别的东西。",
        "answer": (
            "他和一群人乘热气球飞越沙漠，途中气球漏气下坠，必须减重。"
            "大家抽火柴决定谁跳下去，抽到最短的人跳。他手里攥着的，"
            "就是那半根被折断的“最短的火柴”。"
        ),
    },
    {
        "id": "turtle-soup",
        "title": "海龟汤（这个名字的由来）",
        "difficulty": "困难",
        "tags": ["经典", "偏暗"],
        "surface": (
            "他在餐厅点了一碗海龟汤，只喝了一口，勺子就掉在了桌上。"
            "他终于明白，很多年前在海上漂流时，同伴端给他的那碗“海龟汤”，到底是什么了。"
        ),
        "answer": (
            "当年海上遇难，几个人在救生筏上漂流，食物早已耗尽。"
            "同伴说捕到了海龟、煮了汤给他喝，他因此活了下来。"
            "今天他第一次喝到真正的海龟汤，才尝出味道完全不同——当年那碗里，不是海龟。"
        ),
    },
]


def pick_from(
    pool: list[dict],
    difficulty: str | None = None,
    exclude: list[str] | None = None,
) -> dict | None:
    """从给定题库里随机取一道。

    为什么单独抽出来：题库现在有两个来源 —— 内置的 SOUPS，以及玩家
    「加入题库」的 AI 题（存在数据库里）。两者必须共用同一套筛选规则，
    否则「换一题」的行为会随题目来源变化，玩家能明显感觉到不一致。
    """
    candidates = [s for s in pool if not difficulty or s["difficulty"] == difficulty]
    if not candidates:
        candidates = list(pool)  # 该难度一道都没有 → 放宽成全部
    if exclude:
        filtered = [s for s in candidates if s["id"] not in exclude]
        if filtered:
            candidates = filtered
    return random.choice(candidates) if candidates else None


def pick(difficulty: str | None = None, exclude: list[str] | None = None) -> dict | None:
    """只从内置题库里抽（保留原行为，方便单独调用）。"""
    return pick_from(SOUPS, difficulty=difficulty, exclude=exclude)


def get(soup_id: str) -> dict | None:
    return next((s for s in SOUPS if s["id"] == soup_id), None)


def public_view(soup: dict) -> dict:
    """给前端的版本：**去掉汤底**。"""
    return {
        "id": soup["id"],
        "title": soup["title"],
        "difficulty": soup["difficulty"],
        "tags": soup["tags"],
        "surface": soup["surface"],
    }


def difficulties(pool: list[dict] | None = None) -> list[str]:
    """可选难度列表。传 pool 时按合并后的题库统计（内置题 + 收藏的 AI 题）。"""
    seen: list[str] = []
    for s in (SOUPS if pool is None else pool):
        if s["difficulty"] not in seen:
            seen.append(s["difficulty"])
    return seen
