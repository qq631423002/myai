"""聊天相关路由：会话/消息 CRUD + 流式聊天（带持久化）。

每个用户只能看到自己的会话和消息（按 session 里的 user_id 过滤）。
流式协议（SSE，每帧 `data: xxx`）：
  [CONV]123  → 本次对话使用的会话 id（自动新建时前端需要拿到）
  [THINK]    → 后续帧是思考过程
  [ANSWER]   → 后续帧是回答正文
  [DONE]     → 结束

两种聊天入口：
  POST /api/chat        登录用户：历史从数据库取，问答都落库，会话归自己所有
  POST /api/chat/guest  游客：不鉴权、不落库，历史上下文由前端传过来
                        （游客的记录前端存在浏览器的 sessionStorage 里）

AI 调用走 DeepSeek Responses API 的异步流式：
  await client.responses.create(..., stream=True) → async for event in stream
事件名与 OpenAI 一致：response.reasoning_text.delta / response.output_text.delta
"""
import asyncio
import json
from typing import List, Optional

from common.config import api_key, api_base_url, model_name
from common.openapi import SSE_RESPONSES
from common.sse import sse_frame
from database import get_db, SessionLocal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from models import Conversation, Message
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session
from tools import TOOLS
from tools import describe as describe_tool
from tools import execute as execute_tool

router = APIRouter(tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

# 一次问答里最多允许模型连续调几轮工具（防止它反复查、停不下来）
MAX_TOOL_ROUNDS = 3

# 系统提示（Responses API 里的 instructions 参数）。
#
# 为什么需要它？两件事：
#   1) 语言：推理模型默认经常用英文「思考」（英文推理语料占比高），
#      哪怕你问的是中文。历史消息里没有任何中文约束，所以思考过程会中英混杂。
#      这里明确要求「思考过程也用中文」，成本几乎为零，能显著改善。
#      注意：这是「引导」不是「强制」——推理通道不受输入直接控制，
#      偶尔仍可能出现英文，这是模型自身行为，不是代码问题。
#   2) 工具：后端接了天气/路线/时间等真实接口，
#      不提醒的话模型有时会凭记忆编造气温和时间。
CHAT_INSTRUCTIONS = (
    "你是一个中文 AI 助手。"
    "无论用户用什么语言提问，都请全程使用简体中文：正式回答用简体中文，"
    "思考（推理）过程也用简体中文，不要用英文思考。"
    "当调用了工具时，必须依据工具返回的真实数据来回答，不要凭记忆编造。"
)

# 会话标题最长多少字（前端输入框也限制成这个数）
MAX_TITLE_LENGTH = 50


class ConversationCreate(BaseModel):
    title: Optional[str] = "新对话"


class ChatRequest(BaseModel):
    """流式聊天请求体。用模型类而不是 dict，Apifox / Swagger 导入后才能看到字段。

    conversation_id 不传时自动新建会话（标题取问题前 20 字）。
    """
    input: str = ""
    conversation_id: Optional[int] = None


class GuestHistoryItem(BaseModel):
    """游客带上来的一条历史消息。"""
    role: str = "user"
    content: str = ""


class GuestChatRequest(BaseModel):
    """游客流式聊天请求体。

    游客没有数据库会话，所以历史上下文由前端从浏览器里读出来一起传上来。
    """
    input: str = ""
    history: List[GuestHistoryItem] = []


def _require_user_id(request: Request) -> int:
    """未登录直接 401，返回当前用户 id。"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    return user_id


def _conversation_to_dict(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "user_id": conv.user_id,
        "title": conv.title,
        "created_at": str(conv.created_at),
    }


def _message_to_dict(msg: Message) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "role": msg.role,
        "content": msg.content,
        "created_at": str(msg.created_at),
    }


# ===== 会话 CRUD（只操作当前登录用户的数据）=====

@router.get("/api/conversations")
def list_conversations(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(request)
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.id.desc())
        .all()
    )
    return [_conversation_to_dict(c) for c in convs]


@router.post("/api/conversations")
def create_conversation(body: ConversationCreate, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(request)
    conv = Conversation(title=body.title or "新对话", user_id=user_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)  # 获取自增长的 ID
    return _conversation_to_dict(conv)


@router.get("/api/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(request)
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )
    return [_message_to_dict(m) for m in msgs]


@router.patch("/api/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    body: ConversationCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """改会话标题。只能改自己的会话。"""
    user_id = _require_user_id(request)
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if len(title) > MAX_TITLE_LENGTH:
        raise HTTPException(status_code=400, detail=f"标题最多 {MAX_TITLE_LENGTH} 个字")

    conv.title = title
    db.commit()
    db.refresh(conv)
    return _conversation_to_dict(conv)


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, request: Request, db: Session = Depends(get_db)):
    """删除一个会话。只能删自己的；该会话下的所有消息一并级联删除。"""
    user_id = _require_user_id(request)
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    # Conversation.messages 配了 cascade="all, delete-orphan"，删会话会自动删消息
    db.delete(conv)
    db.commit()
    return {"ok": True}


def _save_assistant(conversation_id: int, content: str) -> None:
    """把助手回复落库。

    新开一个数据库会话，避免和请求级的 session 生命周期冲突
    （流式响应可能在请求 session 关闭之后才结束）。
    一个字都没生成出来就不存了。
    """
    if not content.strip():
        return
    _db = SessionLocal()
    try:
        _db.add(
            Message(conversation_id=conversation_id, role="assistant", content=content)
        )
        _db.commit()
    finally:
        _db.close()


async def _stream_answer(api_messages: list, holder: dict):
    """把模型的流式回复包成 SSE 帧发出去，并把完整正文写进 holder["answer"]。

    登录用户和游客共用这段逻辑：这里只负责「调模型 + 调工具 + 发帧」，
    要不要落库、怎么取历史，由各自的接口决定。

    工具调用（Function Calling）怎么走：
      第 1 轮：把用户问题和「工具清单」一起给模型 → 模型可能回一个 function_call
                （比如 get_weather({"city":"北京"})）
      然后    ：我们自己执行这个 Python 函数，把结果以 function_call_output 回传
      下一轮  ：模型拿到真实数据，写出最终回答
      最多循环 MAX_TOOL_ROUNDS 轮，防止模型反复调工具停不下来
    """
    _full_answer = ""
    try:
        # 没配 key 时给出明确原因，而不是让流静悄悄断掉（前端会显示成一片空白）
        if not api_key:
            raise RuntimeError(
                "未配置 API_KEY：请在 backend/.env 里写 API_KEY=sk-xxx，"
                "或设置 myapikey 环境变量后重启后端服务"
            )

        # 异步客户端：await 创建流，再用 async for 消费，不会阻塞事件循环
        client = AsyncOpenAI(api_key=api_key, base_url=api_base_url)
        input_items = list(api_messages)

        for _round in range(MAX_TOOL_ROUNDS + 1):
            # 每一轮都重置标记：这样每轮都会重新下发 [THINK]/[ANSWER]，
            # 前端才知道后面的内容是「思考」还是「正文」（多轮时会来回切换）。
            _think_ = False
            _answer_ = False

            stream = await client.responses.create(
                model=model_name,
                input=input_items,       # 历史上下文 / 上一轮的工具结果
                instructions=CHAT_INSTRUCTIONS,  # 系统提示：语言与工具使用约束
                tools=TOOLS,              # 工具清单，模型据此决定要不要调
                stream=True,
            )

            finished = None
            async for event in stream:
                # 思考过程（Responses API 事件名，与 OpenAI 一致）
                if event.type == "response.reasoning_text.delta":
                    if not _think_:
                        _think_ = True
                        yield sse_frame("[THINK]")
                    yield sse_frame(event.delta)
                # 回答正文
                elif event.type == "response.output_text.delta":
                    if not _answer_:
                        _answer_ = True
                        yield sse_frame("[ANSWER]")
                    _full_answer += event.delta
                    yield sse_frame(event.delta)
                # 流结束时这里带着完整的 response（含 reasoning / message / function_call）
                elif event.type == "response.completed":
                    finished = event.response

            if finished is None:
                break

            tool_calls = [i for i in finished.output if getattr(i, "type", None) == "function_call"]
            if not tool_calls:
                break  # 这一轮没有工具调用 → 它已经是最终回答了

            # 把这一轮的输出原样带上（含 function_call 的 call_id），再追加工具结果
            input_items = [*input_items, *[i.model_dump() for i in finished.output]]

            for call in tool_calls:
                args = {}
                if call.arguments:
                    try:
                        args = json.loads(call.arguments)
                    except json.JSONDecodeError:
                        args = {}
                # 先告诉前端「我在查什么」，否则用户会对着「正在输入…」干等
                yield sse_frame(f"[TOOL]{describe_tool(call.name, args)}")
                output = await execute_tool(call.name, args)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )
    except asyncio.CancelledError:
        # 用户点了「停止生成」：把已经生成的部分记进 holder 交给调用方落库，
        # 否则界面留着半截回答、刷新后却没了，前后对不上。
        holder["answer"] = _full_answer
        raise
    except Exception as exc:  # noqa: BLE001
        # 鉴权失败 / 模型名错误 / 网络异常等，都要当成正文回给前端，
        # 否则界面上只会看到「问了没反应」，无从排查。
        note = f"⚠️ 调用大模型失败：{exc}"
        _full_answer = f"{_full_answer}\n\n{note}" if _full_answer else note
        yield sse_frame("[ANSWER]")
        yield sse_frame(note)

    holder["answer"] = _full_answer
    yield sse_frame("[DONE]")


# ===== 流式聊天（登录用户：带持久化 + 数据库历史）=====

@router.post("/api/chat", responses=SSE_RESPONSES)
async def chat(params: ChatRequest, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(request)
    _input = params.input.strip()
    if not _input:
        raise HTTPException(status_code=400, detail="输入不能为空")

    if params.conversation_id:
        # 校验会话存在且属于当前用户
        conversation_id = params.conversation_id
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        # 没带会话 id：自动新建，标题取问题前 20 个字
        conv = Conversation(title=_input[:20], user_id=user_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id

    # 保存用户消息
    db.add(Message(conversation_id=conversation_id, role="user", content=_input))
    db.commit()

    # 带上历史消息（含刚保存的这条），让 AI 有上下文记忆
    # Responses API 的 input 直接接收 [{"role": ..., "content": ...}]，无需转换
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )
    api_messages = [{"role": m.role, "content": m.content} for m in history]

    holder: dict = {}

    async def event_stream():
        # 先下发会话 id（前端自动新建会话时需要拿到它）
        yield sse_frame(f"[CONV]{conversation_id}")

        try:
            async for frame in _stream_answer(api_messages, holder):
                yield frame
        except asyncio.CancelledError:
            # 用户点了「停止生成」→ 客户端断开 → 这个生成器被取消。
            # 这里要**把已经生成的部分照样落库**，不然界面上留着半截回答、
            # 刷新后却没了，前后对不上。
            #
            # 注意：这里**不能 await**。取消作用域还在生效，一 await 就立刻又抛
            # CancelledError，落库根本执行不到，所以用同步方式存。
            _save_assistant(conversation_id, holder.get("answer", ""))
            raise
        else:
            # 流正常结束（或中途出错，错误也会被当成正文）→ 保存助手回复
            _save_assistant(conversation_id, holder.get("answer", ""))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ===== 游客聊天（不鉴权、不落库）=====

@router.post("/api/chat/guest", responses=SSE_RESPONSES)
async def chat_guest(params: GuestChatRequest):
    """游客聊天：完全不写数据库，历史上下文由前端从浏览器本地存储带上来。"""
    _input = params.input.strip()
    if not _input:
        raise HTTPException(status_code=400, detail="输入不能为空")

    # 只接受合法角色，并丢掉空内容，避免前端传来脏数据
    api_messages = [
        {"role": item.role if item.role in ("user", "assistant") else "user", "content": item.content}
        for item in params.history
        if item.content
    ]
    api_messages.append({"role": "user", "content": _input})

    holder: dict = {}

    async def event_stream():
        async for frame in _stream_answer(api_messages, holder):
            yield frame
        # 这里【故意】不写数据库：游客的记录只留在浏览器里

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
