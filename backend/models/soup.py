"""AI 现场生成的「海龟汤」题。

为什么单独存一张表：
  内置题库写在代码里（game/soups.py），不需要入库；
  但 AI 现编的题，**汤底不能让前端拿到**，又得在玩家后续每次提问时能查回来，
  所以落库保存。（顺带你可以在 Navicat 里看看 AI 都出了些什么题。）

saved 字段是干什么的：
  AI 出的题默认只是「存档」（saved=False），玩完就完了 ——
  因为模型出题质量参差不齐，全塞进抽题池会拉低游戏体验。
  玩家觉得这题好，点「加入题库」才会置为 True，
  之后「换一题」才会把它当成正规题目抽出来。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from database import Base


class GeneratedSoup(Base):
    """AI 现场出的一道海龟汤。"""
    __tablename__ = "generated_soups"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(64), nullable=False)
    surface = Column(Text, nullable=False)  # 汤面：可以给玩家看
    answer = Column(Text, nullable=False)   # 汤底：只在后端，绝不发给前端
    difficulty = Column(String(16), default="中等")
    tags = Column(String(64), default="AI 原创")
    # 是否已「加入题库」：只有加过的题才会进入「换一题」的抽取范围
    saved = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
