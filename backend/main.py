import uvicorn
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from database import Base, engine, ensure_columns
import models  # noqa: F401  确保实体类注册到 Base，才能建表
from common.config import secret_key
from common.paths import AVATAR_DIR, UPLOAD_DIR

app = fastapi.FastAPI(title="AI 聊天后端")

# CORS：配合前端 Vite 代理时不是必需，这里保留以便直接跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session 中间件
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    session_cookie="xx_session",
    max_age=14 * 24 * 3600,
    same_site="lax",
    https_only=False,
)

# 注册支路由
from routers import demo, auth, chat, features, soup, book  # noqa: E402
app.include_router(demo.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(features.router)  # 天气页 / 路线页用的普通接口
app.include_router(soup.router)      # 海龟汤游戏
app.include_router(book.router)      # AI 读书陪读（RAG：上传书 + 带页码引用的问答）
# 注：语音输入已改为前端用浏览器 Web Speech API 实现，后端不再需要 ASR 接口

# 建表（数据库不可用时打印警告并跳过，不影响 demo 接口）
try:
    Base.metadata.create_all(bind=engine)
    ensure_columns()  # 给老库补上后来新增的字段（display_name / avatar）
    print("[init] 数据库表已就绪")
except Exception as e:  # noqa: BLE001
    print(f"[warn] 数据库初始化失败（demo 接口不受影响）：{e}")

# 处理上次没建完的书籍索引（否则前端会一直停在「建索引中」）
try:
    book.recover_stuck_books()
except Exception as e:  # noqa: BLE001
    print(f"[warn] 检查未完成索引时出错（不影响其他功能）：{e}")

# 头像等上传文件的静态目录，先建出来再挂载（StaticFiles 要求目录已存在）
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
# 挂在 /api/uploads 下面，是为了复用前端已有的 vite 代理规则（只代理 /api），
# 不用再去改 vite.config.ts。访问示例：GET /api/uploads/avatars/1_ab12cd34.png
app.mount("/api/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get('/')
def read_root():
    return {'Hello': 'World'}


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8000)
