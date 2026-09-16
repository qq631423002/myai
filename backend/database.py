import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# 读取 .env 文件
load_dotenv()

# 获取数据库连接字符串
# 未配置时回退到本地 SQLite，方便开箱即用（demo 接口不依赖 MySQL）
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# 初始化数据库
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 获取数据库对象
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 新增字段时在这里登记，启动时自动补到老表上。
# 为什么需要它：Base.metadata.create_all() 只会「建缺失的表」，
# 对已存在的表【不会】加列，所以老数据库直接跑新代码会报 no such column。
# ALTER TABLE ADD COLUMN 是 SQLite 和 MySQL 都支持的写法，够学习项目用。
NEW_COLUMNS = {
    "users": {
        "display_name": "VARCHAR(64)",
        "avatar": "VARCHAR(255)",
    },
    "books": {
        "stored_name": "VARCHAR(255)",
    },
    "generated_soups": {
        # 是否已「加入题库」。老库里的历史题目一律按 0（未加入）处理，
        # 不会凭空进入抽题池 —— 由玩家自己决定哪些题值得留下。
        "saved": "BOOLEAN NOT NULL DEFAULT 0",
    },
}


def ensure_columns() -> None:
    """把 NEW_COLUMNS 里登记的新列补到已存在的表上（可重复执行）。"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            if table not in tables:
                continue  # 表还不存在，create_all 会直接按新结构建好
            have = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    print(f"[migrate] 已给 {table} 表补上字段：{name}")
