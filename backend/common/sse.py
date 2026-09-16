"""SSE 相关的工具函数。"""


def sse_frame(data: str) -> str:
    """把一个可能包含换行的文本包成合法的 SSE 帧。

    SSE 规范要求事件里的每一行都要以 `data:` 开头。如果直接把含换行的文本写在
    `data: ` 后面，换行之后的内容会被解析器当作「未知字段」丢掉，回答会被截断
    （模型输出 markdown 时几乎必然出现换行）。

    例：`"a\\nb"` → `"data: a\\ndata: b\\n\\n"`，解析后仍是 `"a\\nb"`。
    """
    return "".join(f"data: {line}\n" for line in data.split("\n")) + "\n"
