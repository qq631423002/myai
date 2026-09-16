"""OpenAPI 文档相关的公共声明。"""

# SSE 响应声明：让 /docs 与 Apifox 知道该接口返回的是 text/event-stream 事件流。
# 说明：FastAPI 默认不会描述 StreamingResponse 的内容类型，加了这个才会在
# OpenAPI 里出现 text/event-stream，Apifox 导入后也能正确识别为流式接口。
SSE_RESPONSES = {
    200: {
        "description": "SSE 事件流，每帧形如 `data: xxx`，以空行分隔",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}
