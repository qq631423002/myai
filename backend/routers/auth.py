"""注册 / 登录 / 退出 / 个人资料 —— 账号信息落库（users 表），密码用 bcrypt 加密存储。

个人资料相关：
  GET  /api/me              当前登录用户信息（含 display_name / avatar）
  POST /api/profile         改「姓名」（display_name），登录用户名 username 不可改
  POST /api/profile/avatar  上传头像图片（multipart，字段名 file）
"""
from pathlib import Path
from uuid import uuid4

import bcrypt
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.paths import AVATAR_DIR, AVATAR_URL_PREFIX
from database import get_db
from models import User

router = APIRouter(tags=["auth"])

# 头像：允许的图片后缀 + 体积上限
ALLOWED_AVATAR_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_NAME_LENGTH = 20


class AuthBody(BaseModel):
    username: str
    password: str


class ProfileBody(BaseModel):
    """改姓名请求体。只改 display_name（显示名/昵称），登录用的 username 不动。"""
    display_name: str = ""


def _user_to_dict(user: User) -> dict:
    """给前端的用户信息（不含密码）。display_name 为空时由前端回退显示 username。"""
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
    }


def _current_user(request: Request, db: Session) -> User:
    """取当前登录用户；未登录 / 用户已被删 都直接 401。"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="未登录")
    return user


def _hash_password(password: str) -> str:
    """bcrypt 加密，结果 60 字符，带随机盐。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


@router.post("/api/register")
def register(body: AuthBody, request: Request, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="用户名已被注册")

    user = User(username=username, password=_hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # 注册成功即视为登录
    request.session["user_id"] = user.id
    return {"ok": True, **_user_to_dict(user)}


@router.post("/api/login")
def login(body: AuthBody, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip()).first()
    if not user or not _verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    request.session["user_id"] = user.id
    return {"ok": True, **_user_to_dict(user)}


@router.get("/api/me")
def me(request: Request, db: Session = Depends(get_db)):
    return _user_to_dict(_current_user(request, db))


@router.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ===== 改姓名 / 换头像 =====

@router.post("/api/profile")
def update_profile(body: ProfileBody, request: Request, db: Session = Depends(get_db)):
    """改「姓名」。传空字符串表示清空（清空后界面回退显示登录用户名）。"""
    user = _current_user(request, db)

    name = body.display_name.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"姓名最多 {MAX_NAME_LENGTH} 个字")

    user.display_name = name or None
    db.commit()
    db.refresh(user)
    return {"ok": True, **_user_to_dict(user)}


@router.post("/api/profile/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传头像。文件存到 backend/uploads/avatars/，库里只存访问路径。"""
    user = _current_user(request, db)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_AVATAR_SUFFIXES:
        raise HTTPException(status_code=400, detail="头像只支持 png / jpg / jpeg / webp / gif")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传的文件是空的")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="头像不能超过 2MB")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # 文件名带用户 id 和随机串：避免同名覆盖，也方便按用户清理
    filename = f"{user.id}_{uuid4().hex[:8]}{suffix}"
    (AVATAR_DIR / filename).write_bytes(data)

    # 记下旧头像，提交成功后再删文件（只删本服务上传的，不动用户手动填的外链）
    old_url = user.avatar
    user.avatar = f"{AVATAR_URL_PREFIX}/{filename}"
    db.commit()
    db.refresh(user)

    if old_url and old_url.startswith(f"{AVATAR_URL_PREFIX}/"):
        try:
            (AVATAR_DIR / Path(old_url).name).unlink(missing_ok=True)
        except OSError:
            pass  # 旧文件删不掉不影响换头像

    return {"ok": True, **_user_to_dict(user)}
