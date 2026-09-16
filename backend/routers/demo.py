"""流式响应（SSE）示例 —— 对应笔记「五、流式响应（SSE）」。

AI 接口走 DeepSeek（OpenAI 兼容格式），base_url = https://api.deepseek.com
DeepSeek 原生支持 Responses API，流式事件名与 OpenAI 一致：
  response.reasoning_text.delta → 思考过程
  response.output_text.delta    → 回答正文
另外 demo04 走 Chat Completions 格式，方便 Apifox 自动合并流式响应。
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from common.config import api_key, api_base_url, model_name
from common.openapi import SSE_RESPONSES
from common.sse import sse_frame

router = APIRouter(tags=["demo"])


class ChatParams(BaseModel):
    """聊天请求体。用模型类而不是 dict，Apifox / Swagger 导入后才能看到字段。"""
    input: str = ""


# 示例 1：简单字符串流式返回
@router.get("/api/demo01", responses=SSE_RESPONSES)
async def demo01():
    async def event_stream():
        results = ["你好啊，", "这是", "一个测", "试。"]
        for result in results:
            await asyncio.sleep(1)  # 休眠1秒，模拟模型处理时间
            yield sse_frame(result)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 示例 2：DeepSeek Responses API 原始流式
@router.post("/api/demo02", responses=SSE_RESPONSES)
async def demo02(params: ChatParams):
    _input = params.input

    async def event_stream():
        client = OpenAI(api_key=api_key, base_url=api_base_url)
        stream = client.responses.create(
            model=model_name,
            input=_input,
            stream=True,  # ← 启用流式输出
        )
        for event in stream:
            yield sse_frame(event.model_dump_json())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 示例 3：分类处理思考过程和回答
@router.post("/api/demo03", responses=SSE_RESPONSES)
async def demo03(params: ChatParams):
    _input = params.input

    async def event_stream():
        client = OpenAI(api_key=api_key, base_url=api_base_url)
        stream = client.responses.create(
            model=model_name,
            input=_input,
            stream=True,
        )
        _think_ = False
        _answer_ = False
        for event in stream:
            if event.type == "response.reasoning_text.delta":
                if not _think_:
                    _think_ = True
                    yield sse_frame("[THINK]")
                yield sse_frame(event.delta)  # SSE 格式
            if event.type == "response.output_text.delta":
                if not _answer_:
                    _answer_ = True
                    yield sse_frame("[ANSWER]")
                yield sse_frame(event.delta)  # SSE 格式
        yield sse_frame("[DONE]")  # SSE 格式

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 示例 4：DeepSeek Chat Completions 流式（给 Apifox 调试用）
# 返回标准 OpenAI Chat Completions 格式（choices[0].delta.content），
# Apifox 内置规则能自动合并成可读文本，并展示 DeepSeek 的思考过程。
@router.post("/api/demo04", responses=SSE_RESPONSES)
async def demo04(params: ChatParams):
    _input = params.input

    async def event_stream():
        client = OpenAI(api_key=api_key, base_url=api_base_url)
        stream = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": _input}],
            stream=True,
        )
        for chunk in stream:
            yield sse_frame(chunk.model_dump_json())
        yield sse_frame("[DONE]")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
