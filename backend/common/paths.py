"""项目里用到的目录路径。

统一用「基于本文件位置往上推」的绝对路径，这样无论从哪个工作目录启动后端
（IDE、`python main.py`、`pnpm dev:api`），文件和数据库都不会落到意外的地方。
"""
from pathlib import Path

# common/ 的上一级就是 backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent

# 上传文件根目录，以及头像子目录
UPLOAD_DIR = BACKEND_DIR / "uploads"
AVATAR_DIR = UPLOAD_DIR / "avatars"

# 头像对外访问的前缀（对应 main.py 里挂载的静态目录）
AVATAR_URL_PREFIX = "/api/uploads/avatars"
