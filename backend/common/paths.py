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

# 私有数据目录：上传的书籍原文，以及 RAG 向量库。
#
# 为什么不放在 uploads/ 下面：main.py 把 UPLOAD_DIR 整个挂成了静态目录
# （/api/uploads/...，见那里挂载的头像），放进去的话，任何人只要知道文件名
# 就能把别人的书和向量库直接下载走。所以这里单独放 data/，不走静态服务。
DATA_DIR = BACKEND_DIR / "data"
BOOK_DIR = DATA_DIR / "books"    # 上传的书（原始 txt/md）
RAG_DIR = DATA_DIR / "rag"       # Chroma 向量库目录

# 头像对外访问的前缀（对应 main.py 里挂载的静态目录）
AVATAR_URL_PREFIX = "/api/uploads/avatars"
