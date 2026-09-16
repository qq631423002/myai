from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    """用户实体类。"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password = Column(String(128), nullable=False)
    # 显示姓名（昵称）：可以随时改；留空时界面回退显示 username
    display_name = Column(String(64), nullable=True)
    # 头像地址：形如 /api/uploads/avatars/1_ab12cd34.png，没上传过就是 None
    avatar = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
