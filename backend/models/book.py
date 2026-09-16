"""上传的书。

为什么书要落库（而不是像海龟汤那样无状态）：
  上传 + 建向量索引是个慢动作（一本长篇要几十秒），必须有个地方记录
  「索引建好了没、进度多少」，前端才能边等边刷新状态。
  章节目录也存成 JSON —— 前端要展示目录、点章节看原文，不必每次都重新解析全文。

向量本身不在这张表里，存在 Chroma（见 rag/store.py）。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class Book(Base):
    """一本上传的书。"""

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)

    # 归属：登录用户记 user_id；游客记 guest_key（放在 session cookie 里的随机串）。
    # 两者只会有其一有值，查询时按当前身份取。
    user_id = Column(Integer, index=True, nullable=True)
    guest_key = Column(String(64), index=True, nullable=True)

    title = Column(String(255), nullable=False)
    filename = Column(String(255), default="")   # 用户上传时的原始文件名（展示用）
    stored_name = Column(String(255), default="")  # 落在 uploads/books/ 下的实际文件名
    char_count = Column(Integer, default=0)      # 全书字数
    page_count = Column(Integer, default=0)      # 估算页数（1000 字/页）
    chapter_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)     # 切成了多少个检索块

    # 章节目录（JSON 字符串）。每项含 index/title/start_char/end_char/start_page/end_page
    chapters_json = Column(Text, default="[]")

    # 索引状态：indexing（建索引中）/ ready（可问答）/ failed（失败，原因见 error）
    status = Column(String(16), default="indexing", index=True)
    progress = Column(Integer, default=0)        # 0~100
    error = Column(Text, default="")             # 失败原因

    created_at = Column(DateTime, default=datetime.now)
