"""AI 可调用的工具（Function Calling）注册表。

以后想加新功能（比如「查快递」「查汇率」），只要做两件事：
  1. 在本目录新建一个模块，提供三样东西：TOOL_SPEC / describe() / run()
  2. 把模块加进下面的 _MODULES
chat.py 里的工具循环、前端的进度提示都不用改。
"""
import json

from tools import route, time_tool, weather

_MODULES = [weather, route, time_tool]

# 给模型看的工具说明书
TOOLS = [m.TOOL_SPEC for m in _MODULES]
_BY_NAME = {m.TOOL_SPEC["name"]: m for m in _MODULES}


def describe(name: str, args: dict) -> str:
    """给前端显示的进度提示。这里出问题也不能影响主流程。"""
    module = _BY_NAME.get(name)
    if not module:
        return f"正在调用 {name}…"
    try:
        return module.describe(**args)
    except Exception:  # noqa: BLE001
        return f"正在调用 {name}…"


async def execute(name: str, args: dict) -> str:
    """执行工具，返回一段 JSON 字符串给模型。

    出错也返回 JSON（而不是抛异常），这样模型能看懂原因并转述给用户，
    比如「没找到地名，请换个城市名」。
    """
    module = _BY_NAME.get(name)
    if not module:
        return json.dumps({"error": f"没有名为 {name} 的工具"}, ensure_ascii=False)
    try:
        result = await module.run(**args)
    except TypeError as exc:
        result = {"error": f"调用 {name} 的参数不对：{exc}"}
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"{name} 执行失败：{exc}"}
    return json.dumps(result, ensure_ascii=False)
