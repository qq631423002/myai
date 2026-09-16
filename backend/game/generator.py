"""让 AI 现场编一道海龟汤。

## 踩过的坑（很重要，别改回去）

1. **必须非流式**：流式会把「汤底」一段段发出去，那就藏不住了。
2. **提示必须短、命令式**：这个模型碰到"开放创作"任务会陷入无休止思考。
   实测用一版 6 条要求 + 10 个"避免重复"标题的长提示时，它思考了 **10 万字**，
   打满 65536 的 reasoning 上限，**正文一个字都没剩下**，耗时 228 秒。
3. **要显式压低思考量**：加 `reasoning={"effort": "low"}` 之后，
   耗时 228s → 34s，思考 65536 → 5084 tokens，正文正常。
   （不传这个参数时，"想多久"完全看运气，有时 2 千字，有时 10 万字。）
4. **要设请求超时**：不然一次跑飞的请求会挂 4 分钟。
"""
import json
import re

from openai import AsyncOpenAI

from common.config import api_base_url, api_key, model_name

# 单次请求最长等多久（秒）。effort=low 时实测约 35 秒，留足余量。
REQUEST_TIMEOUT = 150.0
# 关键参数：把思考量压到 low，避免思考打满上限导致正文为空
REASONING_EFFORT = "low"

# 短、命令式的提示。别写太长，越长它越纠结。
RULES = """你是海龟汤出题人。立刻出一道原创题，只输出 JSON，不要解释、不要代码块：
{"title":"标题","surface":"汤面(2~3句反常的情境)","answer":"汤底(一段话说清真相)","difficulty":"简单","tags":["标签"]}

要求：
- 汤面要让人觉得反常、想追问"为什么"；汤底要能靠是/否提问一步步问出来，逻辑自洽
- 难度定为：__DIFFICULTY__
- 不要涉及自杀、自残、血腥
- 不要用这几个常见套路：打嗝、电梯按钮、沙漠里的潜水员、半根火柴、海龟汤本身
- 尽量别和这些已有的题重复：__AVOID__"""


def _extract_json(text: str) -> dict | None:
    """从模型输出里抠出 JSON（容错：可能带 ``` 包裹或前后有废话）。"""
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(t[start : end + 1])
    except json.JSONDecodeError:
        return None


def _normalize(data: dict, fallback_difficulty: str | None) -> dict | None:
    """校验并整理模型返回的字段。不合格返回 None。"""
    title = str(data.get("title") or "").strip()
    surface = str(data.get("surface") or "").strip()
    answer = str(data.get("answer") or "").strip()
    if not title or not surface or not answer:
        return None

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()][:3] or ["AI 原创"]

    return {
        "title": title[:60],
        "surface": surface,
        "answer": answer,
        "difficulty": str(data.get("difficulty") or fallback_difficulty or "中等")[:10],
        "tags": tags,
    }


async def _one_call(prompt: str) -> str:
    """调一次模型，返回正文（可能为空字符串）。"""
    client = AsyncOpenAI(api_key=api_key, base_url=api_base_url, timeout=REQUEST_TIMEOUT)
    resp = await client.responses.create(
        model=model_name,
        instructions=prompt,
        input="请出题。",
        stream=False,  # 必须非流式
        reasoning={"effort": REASONING_EFFORT},  # 关键：压低思考量
    )
    return "".join(
        c.text for i in resp.output if getattr(i, "type", None) == "message" for c in i.content
    )


async def generate(difficulty: str | None = None, avoid_titles: list[str] | None = None) -> dict:
    """让模型现场编一道题。

    成功返回 {"title","surface","answer","difficulty","tags"}，失败返回 {"error": "原因"}。
    """
    if not api_key:
        return {"error": "未配置 API_KEY，无法让 AI 出题"}

    # 避免清单只给最近几道，太长会让它纠结
    avoid = "、".join(avoid_titles[:6]) if avoid_titles else "（暂无）"
    prompt = RULES.replace("__DIFFICULTY__", difficulty or "随机").replace("__AVOID__", avoid)

    last_error = ""
    # 空正文 / JSON 不合法时重试一次（这类模型的输出偶尔会跑飞）
    for attempt in range(2):
        try:
            text = await _one_call(prompt)
        except Exception as exc:  # noqa: BLE001
            last_error = f"调用模型失败：{exc}"
            continue

        if not text.strip():
            last_error = "模型这次思考太久、没写出题（已重试一次）"
            continue

        data = _extract_json(text)
        made = _normalize(data, difficulty) if data else None
        if made:
            return made
        last_error = f"AI 出的题格式不对。原始输出：{text[:100]}"

    return {"error": last_error or "AI 出题失败，请再试一次"}
