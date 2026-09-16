"""AI 读书陪读：上传书 → 建 RAG 索引 → 带页码引用问答。

定位（与「AI 聊天」「天气」「路线」「海龟汤」并列的独立功能）：
  不把整本书塞给大模型（会远超上下文），而是先按向量检索找出书里最相关的几段，
  再把原文片段作为「依据」交给模型，让它：
    - 只根据书里的内容回答，不编造情节
    - 标出「第几章 · 第几页」的定位
    - 能按章节生成导读

身份与隔离：
  登录用户按 user_id 存书；游客按 session 里的 guest_key 存书。
  游客的书在会话失效后会失去归属（不会自动清理），这是学习项目的取舍。

索引为什么是异步的：
  一本长篇要切几千块、逐块转向量（纯 CPU 约 26 段/秒），要几十秒。
  所以上传时先落库 status=indexing，用 BackgroundTasks 在后台建索引，
  前端轮询 /api/books 就能看到进度。
"""
import json
import secrets
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from common.config import api_base_url, api_key, model_name
from common.openapi import SSE_RESPONSES
from common.paths import BOOK_DIR
from common.sse import sse_frame
from database import SessionLocal, get_db
from models import Book
from rag import reader, store

router = APIRouter(tags=["book"])

BOOK_DIR.mkdir(parents=True, exist_ok=True)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

# 上传限制
MAX_BOOK_BYTES = 50 * 1024 * 1024  # 50MB，纯文本的书足够用
ALLOWED_SUFFIXES = {".txt", ".md"}

# 检索参数
TOP_K = 6                    # 普通提问：取回最相关的几块
# 用户点名某一章时（「第四章讲了什么」），要覆盖整章才好做概括，
# 所以给得比普通提问多；上限仍受 MAX_CONTEXT_CHARS 约束。
CHAPTER_TOP_K = 22
MAX_CONTEXT_CHARS = 20000    # 拼给模型的原文总量上限，防止超出上下文

# 系统提示：把检索到的原文片段作为唯一依据，并要求标注章节和页码
BOOK_INSTRUCTIONS = """你是一位「AI 读书陪读」。请把自己当成刚刚读完了《{book_title}》这本书的人，直接回答读者的问题。

【当前书籍】{book_title}

【下面是从书中取出的相关内容】
{context}

【回答要求】
1. 直接回答问题本身。不要在开头交代你的信息从哪来、依据了什么材料，也不要说明这些内容是怎么选出来的。
2. 严禁出现下面这类交代信息来源的话（以及意思相近的变体）：
   - 「我手头能依据的只是若干片段」「并非全书全文」
   - 「仅就这些片段来看」「以上只是被检索到的部分内容」
   - 「根据提供的上下文/资料/片段」「我没有完整的书」
   读者不需要知道这些，直接给结论即可。
3. 如果下面确实没有回答问题所需的信息，就用一句话淡淡带过，例如「书中没有提到这一点」，然后继续回答你能回答的部分。
   不要长篇解释你为什么答不上来，也不要罗列你缺少什么。
4. 回答用到了具体内容时，在相应句子末尾标注来源，格式为（第X章·第Y页）。章节名和页码照抄下面给出的信息，不要自己另编。
5. 问某一章讲了什么时，把该章内容概括成条理清楚的要点；能确定是全书层面的问题（如主题、人物关系、整体走向）时，可以综合作答，但不要虚构书里没有的情节。
6. 全程使用简体中文，语气像一位耐心、克制的阅读助手。开头直接进入正题，不要有「好的」「根据您的要求」这类铺垫。"""


# ===== 请求 / 响应结构 =====

class BookSummary(BaseModel):
    id: int
    title: str
    filename: str
    char_count: int
    page_count: int
    chapter_count: int
    chunk_count: int
    status: str
    progress: int
    error: str
    created_at: str


class ChapterInfo(BaseModel):
    index: int
    title: str
    start_char: int
    end_char: int
    start_page: int
    end_page: int


class BookDetail(BookSummary):
    chapters: list[ChapterInfo] = []


class AskBookRequest(BaseModel):
    """对书提问。history 由前端带上来（后端不存读书的问答记录）。"""
    book_id: int
    input: str = ""
    history: list[dict] = []


class RebuildIndexRequest(BaseModel):
    book_id: int


# ===== 身份辅助 =====

def _identity(request: Request) -> tuple[Optional[int], str]:
    """返回 (user_id 或 None, guest_key)。

    游客没有账号，用一个存在 session 里的随机串来标记「这些书是他的」。
    """
    user_id = request.session.get("user_id")
    if user_id:
        return int(user_id), ""
    guest_key = request.session.get("guest_key")
    if not guest_key:
        guest_key = "guest_" + secrets.token_hex(16)
        request.session["guest_key"] = guest_key
    return None, guest_key


def _scope(query, request: Request):
    """给查询加上「只查当前用户的书」条件。"""
    user_id, guest_key = _identity(request)
    if user_id:
        return query.filter(Book.user_id == user_id)
    return query.filter(Book.guest_key == guest_key)


def _get_book_or_404(book_id: int, request: Request, db: Session) -> Book:
    book = _scope(db.query(Book).filter(Book.id == book_id), request).first()
    if not book:
        raise HTTPException(status_code=404, detail="书不存在，或你没有访问权限")
    return book


def _book_summary(book: Book) -> BookSummary:
    return BookSummary(
        id=book.id,
        title=book.title,
        filename=book.filename or "",
        char_count=book.char_count or 0,
        page_count=book.page_count or 0,
        chapter_count=book.chapter_count or 0,
        chunk_count=book.chunk_count or 0,
        status=book.status or "indexing",
        progress=book.progress or 0,
        error=book.error or "",
        created_at=str(book.created_at),
    )


def _book_detail(book: Book) -> BookDetail:
    base = _book_summary(book)
    try:
        chapters = json.loads(book.chapters_json or "[]")
    except json.JSONDecodeError:
        chapters = []
    return BookDetail(**base.model_dump(), chapters=chapters)


# ===== 书籍列表 / 详情 =====

@router.get("/api/books")
def list_books(request: Request, db: Session = Depends(get_db)):
    """当前身份（登录用户或游客）的书架。前端靠它轮询索引进度。"""
    books = _scope(db.query(Book), request).order_by(desc(Book.created_at)).all()
    return [_book_summary(b) for b in books]


@router.get("/api/books/{book_id}")
def get_book(book_id: int, request: Request, db: Session = Depends(get_db)):
    """一本书的详情 + 章节目录。"""
    return _book_detail(_get_book_or_404(book_id, request, db))


@router.get("/api/books/{book_id}/chapter/{chapter_index}")
def get_chapter(
    book_id: int,
    chapter_index: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """读取某一章的原文，用于「点目录看原文」。

    这里按需从原始文件里切出该章，不把全文存进数据库（省空间）。
    """
    book = _get_book_or_404(book_id, request, db)
    path = BOOK_DIR / (book.stored_name or "")
    if not book.stored_name or not path.exists():
        raise HTTPException(status_code=404, detail="原始文件已丢失，无法读取原文")

    try:
        parsed = reader.parse_bytes(book.filename or "book.txt", path.read_bytes())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for chap in parsed.chapters:
        if chap.index == chapter_index:
            return {
                "index": chap.index,
                "title": chap.title,
                "content": chap.content,
                "start_page": chap.start_page,
                "end_page": chap.end_page,
                "char_count": chap.char_count,
            }
    raise HTTPException(status_code=404, detail="没有这一章")


# ===== 上传 / 重建 / 删除 =====

@router.post("/api/books/upload")
async def upload_book(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传 txt/md 书：先解析入库（快），再后台建向量索引（慢）。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="只支持 .txt / .md 文件")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容是空的")
    if len(data) > MAX_BOOK_BYTES:
        raise HTTPException(status_code=400, detail="文件不能超过 50MB")

    # 解析：章节、字数、页数都在这一步算出来（不依赖模型，很快）
    try:
        parsed = reader.parse_bytes(file.filename or "未命名.txt", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id, guest_key = _identity(request)

    # 原始文件按随机名落盘，供「重建索引」和「读某章原文」复用。
    # 用随机名而不是原文件名：避免路径穿越，也避免同名互相覆盖。
    stored_name = f"{secrets.token_hex(12)}{suffix}"
    (BOOK_DIR / stored_name).write_bytes(data)

    book = Book(
        user_id=user_id,
        guest_key=guest_key,
        title=parsed.title or Path(file.filename or "").stem or "未命名",
        filename=file.filename or "",
        stored_name=stored_name,
        char_count=parsed.total_chars,
        page_count=parsed.total_pages,
        chapter_count=parsed.chapter_count,
        chunk_count=0,
        chapters_json=json.dumps(
            [
                {
                    "index": c.index,
                    "title": c.title,
                    "start_char": c.start_char,
                    "end_char": c.end_char,
                    "start_page": c.start_page,
                    "end_page": c.end_page,
                }
                for c in parsed.chapters
            ],
            ensure_ascii=False,
        ),
        status="indexing",
        progress=0,
        error="",
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    # 后台建索引：接口先返回，前端轮询列表看 status 变 ready
    background.add_task(_build_index, book.id, parsed)

    return {"book_id": book.id, "title": book.title, "status": book.status}


def recover_stuck_books() -> None:
    """启动时处理上次没建完索引的书。

    为什么要这个：建索引是在后台跑的，如果进程在跑的过程中被杀掉
    （比如关掉终端、Ctrl+C），数据库里的记录会一直停在 status=indexing，
    前端就永远显示「建索引中 0%」，点「重建索引」才能恢复。
    这里把它们标成 failed 并说明原因，用户一看就知道该点重建。
    """
    db = SessionLocal()
    try:
        stuck = db.query(Book).filter(Book.status == "indexing").all()
        for book in stuck:
            book.status = "failed"
            book.error = "上次建索引被中断（后端重启或进程退出），请点「重建索引」重试。"
            # 半途而废的向量库清掉，免得留下残缺索引被搜到
            store.delete_collection(book.id)
        if stuck:
            db.commit()
            print(f"[rag] 已把 {len(stuck)} 本中断索引的书标记为待重建")
    finally:
        db.close()


def _build_index(book_id: int, parsed: reader.ParsedBook) -> None:
    """后台任务：写向量库并更新状态。

    必须新开 DB Session：请求级的 Session 在响应返回时就关了，
    而流式/后台任务可能在之后才跑完（和 chat.py 里的 _save_assistant 同样道理）。
    """
    db = SessionLocal()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return

        def on_progress(percent: int) -> None:
            """建索引过程中上报进度，前端轮询 /api/books 就能看到百分比。"""
            book.progress = percent
            db.commit()

        try:
            chunk_count = store.index_book(book_id, parsed, on_progress=on_progress)
            book.chunk_count = chunk_count
            book.status = "ready"
            book.progress = 100
            book.error = ""
        except Exception as exc:  # noqa: BLE001
            # 建索引失败必须记下来，否则前端只会一直转圈，无从排查
            book.status = "failed"
            book.error = str(exc)[:500]
            # 索引失败时清掉向量库，避免留下半截数据被后续问答搜到
            store.delete_collection(book_id)
        db.commit()
    finally:
        db.close()


@router.post("/api/books/rebuild")
def rebuild_book(
    body: RebuildIndexRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """重建向量索引（换了 embedding 模型，或索引损坏时用）。"""
    book = _get_book_or_404(body.book_id, request, db)
    path = BOOK_DIR / (book.stored_name or "")
    if not book.stored_name or not path.exists():
        raise HTTPException(status_code=404, detail="原始文件已丢失，无法重建索引")

    try:
        parsed = reader.parse_bytes(book.filename or "book.txt", path.read_bytes())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    book.status = "indexing"
    book.progress = 0
    book.error = ""
    db.commit()

    background.add_task(_build_index, book.id, parsed)
    return {"ok": True, "status": "indexing"}


@router.delete("/api/books/{book_id}")
def delete_book(book_id: int, request: Request, db: Session = Depends(get_db)):
    """删书：连同向量库和原始文件一起清理。"""
    book = _get_book_or_404(book_id, request, db)
    stored_name = book.stored_name or ""

    # 先删向量库，再删数据库记录。向量库删失败也不该阻塞删书（rag/store 内部已吞掉异常）
    store.delete_collection(book.id)

    db.delete(book)
    db.commit()

    # DB 记的已删除，最后清理磁盘文件；删不掉不影响结果
    if stored_name:
        try:
            (BOOK_DIR / stored_name).unlink(missing_ok=True)
        except OSError:
            pass

    return {"ok": True}


# ===== 问答（SSE） =====

@router.post("/api/books/ask", responses=SSE_RESPONSES)
async def ask_book(params: AskBookRequest, request: Request, db: Session = Depends(get_db)):
    """对书提问：先向量检索，再让模型只依据检索到的原文回答。"""
    book = _get_book_or_404(params.book_id, request, db)
    if book.status != "ready":
        raise HTTPException(status_code=409, detail="这本书还没建好索引，请稍等片刻再问")

    question = params.input.strip()
    if not question:
        raise HTTPException(status_code=400, detail="请输入你的问题")

    # —— RAG 的检索环节 ——
    # 点名某一章时多取一些块，否则一两千字概括不了整章；
    # store.retrieve 内部会识别「第X章」并走确定性匹配。
    top_k = CHAPTER_TOP_K if store.wanted_chapters(question) else TOP_K
    hits = store.retrieve(book.id, question, top_k=top_k)

    # 历史只保留纯文本，不把上一轮的引用片段再塞回去（会越滚越长）
    history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in params.history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    if not hits:
        # 书里检索不到相关内容：直接告诉用户，别让模型硬编
        return StreamingResponse(
            _stream_plain("书中没有提到相关内容。可以换个说法，或者问问某一章讲了什么。"),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    # 拼接上下文：每块开头标出章节和页码，模型据此写引用
    parts: list[str] = []
    total = 0
    for hit in hits:
        part = (
            f"【第{hit['chapter_index']}章 {hit['chapter_title']} · 第{hit['page']}页】\n"
            f"{hit['text']}"
        )
        if total + len(part) > MAX_CONTEXT_CHARS:
            break
        parts.append(part)
        total += len(part)

    instructions = BOOK_INSTRUCTIONS.format(book_title=book.title, context="\n\n".join(parts))

    # 去重后的来源列表：前端把它渲染成「依据」小标签，点了能跳到该章原文对质。
    # 检索可能命中同一章的多块，所以按（章, 页）去重。
    seen = set()
    sources = []
    for hit in hits:
        key = (hit["chapter_index"], hit["page"])
        if key in seen:
            continue
        seen.add(key)
        sources.append({"chapter_index": hit["chapter_index"], "page": hit["page"]})

    return StreamingResponse(
        _stream_answer(history, question, instructions, sources),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _stream_answer(
    history: list[dict], question: str, instructions: str, sources: list[dict]
):
    """调用模型流式生成，按 [SOURCES] / [THINK] / [ANSWER] / [DONE] 协议下发。

    为什么也转发思考过程：
    模型回答前会先推理，问整本书或某一章时往往要思考几十秒。
    如果这段只字不发，前端就只能干等（用户反馈过「提问后很长时间才有回答」）。
    转发出来后，推理的字会先滚出来，用户能立刻看到它在干什么。

    思考过程和正文用 [THINK] / [ANSWER] 分开标记，前端分两块渲染，
    不会把推理内容混进正式回答里。
    """
    # 先下发引用来源（JSON 一行），前端据此渲染可点击的「依据」标签
    if sources:
        yield sse_frame("[SOURCES]" + json.dumps(sources, ensure_ascii=False))

    if not api_key:
        yield sse_frame("[ANSWER]")
        yield sse_frame(
            "⚠️ 未配置 API_KEY，无法回答。请在 backend/.env 里填写 DeepSeek Key 后重启后端。"
        )
        yield sse_frame("[DONE]")
        return

    client = AsyncOpenAI(api_key=api_key, base_url=api_base_url)
    started = False   # 正文是否已经开始
    thought = False   # 思考过程是否已经开始
    try:
        stream = await client.responses.create(
            model=model_name,
            instructions=instructions,
            input=[*history, {"role": "user", "content": question}],
            stream=True,
        )
        async for event in stream:
            # 思考过程（事件名与 OpenAI Responses API 一致）
            if event.type == "response.reasoning_text.delta":
                if not thought:
                    thought = True
                    yield sse_frame("[THINK]")
                yield sse_frame(event.delta)
            # 回答正文
            elif event.type == "response.output_text.delta":
                if not started:
                    started = True
                    yield sse_frame("[ANSWER]")
                yield sse_frame(event.delta)

        if not started:
            # 只有一个字都没输出时才算异常；只出了思考没有正文，也属于异常
            yield sse_frame("[ANSWER]")
            yield sse_frame("（模型这次没有输出内容，请再问一次）")
    except Exception as exc:  # noqa: BLE001
        # 鉴权失败 / 模型名错误 / 网络异常都要当成正文回给前端，
        # 否则界面只会显示「问了没反应」，无从排查
        yield sse_frame("[ANSWER]")
        yield sse_frame(f"⚠️ 调用大模型失败：{exc}")
    yield sse_frame("[DONE]")


async def _stream_plain(message: str):
    """不下模型、直接返回一段文字的流式实现。"""
    yield sse_frame("[ANSWER]")
    yield sse_frame(message)
    yield sse_frame("[DONE]")
