"""AI 海龟汤：AI 当主持人，玩家问是非题，把真相推理出来。

题目有两个来源：
- **内置题库** game/soups.py（写在代码里，id 形如 water-and-gun）
- **AI 现场出的题**（存在 MySQL 的 generated_soups 表，id 形如 ai-12）

四个设计要点：
1. **汤底只在后端**，前端只能拿到汤面 —— 玩家没法从网络请求里偷看答案
2. **不存游戏过程、不需要登录**，游客直接玩（问答历史由前端带着走，后端无状态）
3. **只转发 [ANSWER]，绝不转发 [THINK]** ——
   模型的思考过程会直接把汤底写出来，转发了就没法玩了
4. **出题必须非流式** —— 流式会把汤底一段段发出去
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.config import api_key, api_base_url, model_name
from common.openapi import SSE_RESPONSES
from common.sse import sse_frame
from database import get_db
from game import generator, soups
from models import GeneratedSoup

router = APIRouter(tags=["soup"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

# AI 出的题最多留这么多道，超了就删最旧的（不然数据库会无限增长）
MAX_GENERATED = 200

# 主持人规则：只能答是/否/无关、绝不泄露汤底、玩家猜答案时判对错
HOST_RULES = """
你是一个「海龟汤」（情境推理）游戏的主持人。玩家要通过问是非题，推理出下面这个故事的真相。

【汤面】（这是给玩家看的）
{surface}

【汤底】（真相。只有你知道，绝对不能在回答里说出来，也不能把关键情节透露给玩家）
{answer}

回答规则（必须严格遵守）：
1. 玩家提问时，你的回答只能以下面三个词之一开头：「是」「否」「无关」。
   后面可以再补一句话，但不超过 25 个字，并且不能透露汤底的关键情节。
2. 即使玩家的问题已经非常接近真相，你也只能回答「是」，不能顺着继续说下去。
3. 玩家如果说「我猜……」或者要求给出答案，你要判断他的完整推理是否基本正确：
   - 基本正确 → 以「猜对了！」开头，然后用充足的篇幅把汤底完整讲清楚，并恭喜他。
   - 不正确 → 以「否」开头，再用一句话（不超过 30 字）指出他推理里最不对的地方。
4. 玩家如果只是闲聊、问规则、或者要提示，可以用「无关」开头简短回应，但依然不能泄露汤底。
5. 不要主动给额外提示，不要复述汤面，保持简洁、神秘。全程用中文回答。"""


class SoupTurn(BaseModel):
    role: str = "user"
    content: str = ""


class AskRequest(BaseModel):
    """一次提问。history 是之前的问答（前端带着走，后端不存）。"""
    id: str
    question: str = ""
    history: List[SoupTurn] = []


class GenerateRequest(BaseModel):
    difficulty: Optional[str] = None


def _load(soup_id: str, db: Session) -> dict | None:
    """按 id 找题：先查内置题库，再查 AI 出的题（id 形如 ai-12）。"""
    builtin = soups.get(soup_id)
    if builtin:
        return builtin

    if soup_id.startswith("ai-"):
        try:
            pk = int(soup_id[3:])
        except ValueError:
            return None
        row = db.query(GeneratedSoup).filter(GeneratedSoup.id == pk).first()
        if row:
            return {
                "id": soup_id,
                "title": row.title,
                "difficulty": row.difficulty or "中等",
                "tags": [t for t in (row.tags or "").split(",") if t] or ["AI 原创"],
                "surface": row.surface,
                "answer": row.answer,
            }
    return None


def _saved_ai_soups(db: Session) -> list[dict]:
    """把玩家「加入题库」的 AI 题转成和内置题库一样的结构。

    转成同一结构，是为了让它们能和内置题一起交给 soups.pick_from() 抽取 ——
    抽题逻辑不需要知道题目来自代码还是数据库。
    """
    rows = (
        db.query(GeneratedSoup)
        .filter(GeneratedSoup.saved.is_(True))
        .order_by(GeneratedSoup.id.asc())
        .all()
    )
    return [
        {
            "id": f"ai-{r.id}",
            "title": r.title,
            "difficulty": r.difficulty or "中等",
            "tags": [t for t in (r.tags or "").split(",") if t] or ["AI 原创"],
            "surface": r.surface,
            "answer": r.answer,
        }
        for r in rows
    ]


@router.get("/api/soup/new")
def new_soup(
    difficulty: Optional[str] = None,
    exclude: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """随机抽一道。**只返回汤面**，汤底留在后端。

    题库 = 内置题库（game/soups.py）+ 玩家「加入题库」的 AI 题。

    为什么 AI 出的题默认不进题库：模型出题质量参差不齐，全塞进抽题池
    会明显拉低游戏体验。所以默认只是存档，由玩家自己点「加入题库」筛选。
    """
    exclude_ids = [x.strip() for x in (exclude or "").split(",") if x.strip()]
    pool = list(soups.SOUPS) + _saved_ai_soups(db)

    picked = soups.pick_from(pool, difficulty=difficulty, exclude=exclude_ids)
    if not picked:
        raise HTTPException(status_code=404, detail="没有可用的题目")

    return {
        "题目": soups.public_view(picked),
        "可选难度": soups.difficulties(pool),
        "题目总数": len(pool),
        "来源": "AI 题库（已收藏）" if picked["id"].startswith("ai-") else "内置题库",
    }


@router.post("/api/soup/generate")
async def generate_soup(body: GenerateRequest, db: Session = Depends(get_db)):
    """让 AI 现场编一道题，存进数据库，然后**只把汤面**返回给前端。

    （出题要写两个故事，比较慢，前端记得显示「AI 正在出题…」。）
    """
    # 把内置题的标题 + 最近 AI 出过的标题 + 已加入题库的标题都告诉它，尽量避免撞车
    avoid = [s["title"] for s in soups.SOUPS]
    recent = (
        db.query(GeneratedSoup.title).order_by(GeneratedSoup.id.desc()).limit(10).all()
    )
    avoid += [r[0] for r in recent]
    # 已收藏的题也报给它：否则可能又出一道跟题库里某道几乎一样的（上限 20 条，别把提示词撑爆）
    saved_titles = (
        db.query(GeneratedSoup.title)
        .filter(GeneratedSoup.saved.is_(True))
        .order_by(GeneratedSoup.id.desc())
        .limit(20)
        .all()
    )
    avoid += [r[0] for r in saved_titles if r[0] not in avoid]

    made = await generator.generate(difficulty=body.difficulty, avoid_titles=avoid)
    if "error" in made:
        raise HTTPException(status_code=502, detail=made["error"])

    row = GeneratedSoup(
        title=made["title"],
        surface=made["surface"],
        answer=made["answer"],
        difficulty=made["difficulty"],
        tags=",".join(made["tags"]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # 只保留最近的 MAX_GENERATED 道，防止表无限增长
    keep = [
        r[0]
        for r in db.query(GeneratedSoup.id)
        .order_by(GeneratedSoup.id.desc())
        .limit(MAX_GENERATED)
        .all()
    ]
    if keep:
        db.query(GeneratedSoup).filter(GeneratedSoup.id.notin_(keep)).delete(
            synchronize_session=False
        )
        db.commit()

    return {
        "题目": {
            "id": f"ai-{row.id}",
            "title": row.title,
            "difficulty": row.difficulty,
            "tags": [t for t in (row.tags or "").split(",") if t],
            "surface": row.surface,
            "saved": bool(row.saved),   # 新出的题默认 False，玩家点「加入题库」才变 True
        },
        "来源": "AI 现场出题",
    }


class SaveRequest(BaseModel):
    """把 AI 出的题加入题库 / 移出题库。"""
    id: str
    saved: bool = True


@router.post("/api/soup/save")
def save_soup(body: SaveRequest, db: Session = Depends(get_db)):
    """把 AI 现场出的题加入题库（或移出）。

    加入后它会和内置题一样被「换一题」抽到；
    移出只是不再进入抽题池，题目记录本身仍然保留（数据库里还能查到）。
    """
    if not body.id.startswith("ai-"):
        raise HTTPException(status_code=400, detail="内置题本来就在题库里，不用加入")
    try:
        pk = int(body.id[3:])
    except ValueError:
        raise HTTPException(status_code=400, detail="题目 id 格式不对")

    row = db.query(GeneratedSoup).filter(GeneratedSoup.id == pk).first()
    if not row:
        raise HTTPException(status_code=404, detail="题目不存在或已被清理（只保留最近 200 道）")

    row.saved = body.saved
    db.commit()
    db.refresh(row)
    return {"id": body.id, "saved": bool(row.saved), "title": row.title}


@router.get("/api/soup/{soup_id}/answer")
def reveal_answer(soup_id: str, db: Session = Depends(get_db)):
    """揭晓汤底（玩家认输时用）。内置题和 AI 出的题都支持。"""
    soup = _load(soup_id, db)
    if not soup:
        raise HTTPException(status_code=404, detail="题目不存在或已过期")
    return {"标题": soup["title"], "汤底": soup["answer"]}


@router.post("/api/soup/ask", responses=SSE_RESPONSES)
async def ask(params: AskRequest, db: Session = Depends(get_db)):
    soup = _load(params.id, db)
    if not soup:
        raise HTTPException(status_code=404, detail="题目不存在或已过期，请换一题")

    question = params.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="请输入你的问题")

    rules = HOST_RULES.format(surface=soup["surface"], answer=soup["answer"])
    history = [
        {"role": t.role if t.role in ("user", "assistant") else "user", "content": t.content}
        for t in params.history
        if t.content
    ]

    async def event_stream():
        try:
            if not api_key:
                raise RuntimeError(
                    "未配置 API_KEY：请在 backend/.env 里写 API_KEY=sk-xxx，"
                    "或设置 myapikey 环境变量后重启后端"
                )

            client = AsyncOpenAI(api_key=api_key, base_url=api_base_url)
            stream = await client.responses.create(
                model=model_name,
                instructions=rules,  # 汤底藏在这里，不会发给前端
                input=[*history, {"role": "user", "content": question}],
                stream=True,
            )

            started = False
            async for event in stream:
                # 只转发正文。绝不转发 response.reasoning_text.delta ——
                # 模型的思考过程会把汤底直接写出来，那就没法玩了。
                if event.type == "response.output_text.delta":
                    if not started:
                        started = True
                        yield sse_frame("[ANSWER]")
                    yield sse_frame(event.delta)

            if not started:
                # 一个字都没输出（异常情况），也得让前端知道该显示什么
                yield sse_frame("[ANSWER]")
                yield sse_frame("（主持人没有作答，请再问一次）")
        except Exception as exc:  # noqa: BLE001
            yield sse_frame("[ANSWER]")
            yield sse_frame(f"⚠️ 主持人走神了：{exc}")

        yield sse_frame("[DONE]")

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
