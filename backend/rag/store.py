"""向量库读写：把书存进 Chroma，再按问题检索相关内容。

设计说明
--------
1. 一本书对应一个 Chroma collection，名字形如 book_{book_id}。
   这样删书 = 删 collection，简单直接，也不用在 where 里再按 book_id 过滤。
2. 用 Chroma 自己的持久化目录（RAG_DIR），不额外存 JSON：
   - 书封面/元数据（标题、章节列表、页码）存在 SQLite（books 表）
   - 检索用的向量块存在 Chroma
3. 所有函数都尽量轻量：index_book 不阻塞主线程太久（分块后逐批写入），
   检索只查 top_k 个块。
"""
import re
import threading

import chromadb
from chromadb.config import Settings

from common.paths import RAG_DIR
from rag import embedding
from rag.embedding import LocalEmbeddingFunction
from rag.reader import ParsedBook, split_chunks

# Chroma 持久化目录，启动时建好
RAG_DIR.mkdir(parents=True, exist_ok=True)

# collection 名不能太短（Chroma 要求至少 3 个字符）
_COLLECTION_PREFIX = "book_"

# 检索默认取回多少块（每块 900 字左右，top 6 大约覆盖 5 千字）
DEFAULT_TOP_K = 6

# 相似度上限（余弦距离：越小越相似，1.0 相当于「正交/不相关」）。
# 这里故意放得比较宽：宁可多给模型几段原文，也不要因为卡太死而漏掉正确片段 ——
# 「书里到底有没有相关内容」交给提示词去判断，比调阈值稳。
MAX_DISTANCE = 1.0

# 写向量时一批多少条。太小慢，太大内存吃紧。
_BATCH_SIZE = 64

# 单本书最多存多少个块（约 900 字/块，≈ 90 万字上限），防止有人上传超大书把内存打爆
MAX_CHUNKS_PER_BOOK = 5000

_client_lock = threading.Lock()
_client = None


def _get_client() -> chromadb.PersistentClient:
    """获取（懒加载 + 加锁）全局 Chroma 客户端。"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(
                    path=str(RAG_DIR),
                    settings=Settings(anonymized_telemetry=False),
                )
    return _client


def _collection_name(book_id: int) -> str:
    return f"{_COLLECTION_PREFIX}{book_id}"


def collection(book_id: int):
    """按书 id 打开 collection。书不存在时返回 None。

    打开时也要带上 embedding_function：Chroma 会把创建时的 EF 配置一起持久化，
    显式传入可以保证「重启进程后再打开」时用的一定是同一个模型，
    也避免它去尝试验证/重建已存的 EF 配置而报错。
    """
    client = _get_client()
    try:
        return client.get_collection(
            name=_collection_name(book_id),
            embedding_function=LocalEmbeddingFunction(),
        )
    except Exception:
        return None


def delete_collection(book_id: int) -> None:
    """删除书的向量库（删书时调用）。"""
    try:
        _get_client().delete_collection(name=_collection_name(book_id))
    except Exception:
        pass


def index_book(book_id: int, parsed: ParsedBook, on_progress=None) -> int:
    """把解析好的书写进向量库，返回写入的块数。

    on_progress(percent) 是可选的进度回调（0~100），前端靠它显示建索引的进度。
    """
    chunks = split_chunks(parsed)
    if not chunks:
        return 0
    if len(chunks) > MAX_CHUNKS_PER_BOOK:
        raise ValueError(
            f"这本书太大：共 {len(chunks)} 块，超过单本上限 {MAX_CHUNKS_PER_BOOK} 块"
        )

    client = _get_client()
    # 先删旧（重复上传同一本书时）
    try:
        client.delete_collection(name=_collection_name(book_id))
    except Exception:
        pass

    col = client.create_collection(
        name=_collection_name(book_id),
        metadata={"hnsw:space": "cosine"},
        embedding_function=LocalEmbeddingFunction(),
    )

    # 分批写入，避免一次塞几千条内存暴涨。
    # 每批写完后回调一次进度：向量化是最慢的一步，分批上报才能让前端看到变化。
    for i in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[i : i + _BATCH_SIZE]

        # 关键：向量化的文本要带上章节标题，但存进 documents 的仍是纯正文。
        #
        # 为什么这么绕：正文里通常不会出现「第四章」这种字样（标题在元数据里），
        # 所以用户问「第四章讲了什么」时，向量根本匹配不上 —— 实测会检索到
        # 别的章节。加上标题前缀后，「第四章 悬赏」这类问法就能命中该章。
        embed_texts = [f"{c['chapter_title']}\n{c['text']}" for c in batch]
        col.add(
            ids=[f"{book_id}-{i + j}" for j in range(len(batch))],
            embeddings=embedding.encode(embed_texts),
            documents=[c["text"] for c in batch],
            metadatas=[
                {
                    "chapter_index": c["chapter_index"],
                    "chapter_title": c["chapter_title"],
                    "page": c["page"],
                    "start_char": c["start_char"],
                    "end_char": c["end_char"],
                }
                for c in batch
            ],
        )
        if on_progress:
            # 留 5% 给最后的收尾，避免进度条卡在 100% 却还在写
            done = min(i + _BATCH_SIZE, len(chunks))
            try:
                on_progress(int(done / len(chunks) * 95) + 5)
            except Exception:  # noqa: BLE001
                pass  # 回调出错不能影响建索引本身
    return len(chunks)


def _retrieve(
    book_id: int,
    query_text: str,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = MAX_DISTANCE,
) -> list[dict]:
    """向量检索：把问题转向量，再在书的 collection 里找最近的块。"""
    col = collection(book_id)
    if col is None:
        return []

    total = col.count()
    if total == 0:
        return []

    query_vec = embedding.encode_one(query_text)
    try:
        res = col.query(
            query_embeddings=[query_vec],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        # 向量库损坏/维度不匹配等异常：当作「没检索到」，让上层走兜底回复，
        # 而不是把整个问答接口打成 500
        return []

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    results = []
    for doc, meta, dist in zip(docs, metas, dists):
        if dist is None or dist > max_distance:
            continue
        results.append(
            {
                "text": doc,
                "distance": float(dist),
                "chapter_index": int(meta.get("chapter_index", 0)),
                "chapter_title": meta.get("chapter_title", ""),
                "page": int(meta.get("page", 1)),
                "start_char": int(meta.get("start_char", 0)),
                "end_char": int(meta.get("end_char", 0)),
            }
        )
    return results


# 中文数字 → 阿拉伯数字（够覆盖长篇小说用到的量级）
# 中文数字字符（「十」「百」是单位，单独在 _number_in 里处理）
_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def _number_in(text: str) -> int | None:
    """把一段文字里的中文/阿拉伯数字转成整数，解析不出返回 None。

    覆盖「四」「十一」「二十二」「一百二十三」这类写法。
    实现要点：遇到单位（十/百）就把「当前累积的数字」乘上去入总账，
    所以「二十二」= 2×10 + 2 = 22（这里最容易写错成 12）。
    """
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    units = {"十": 10, "百": 100}
    total = 0
    current = 0   # 当前待处理的一位数字
    for ch in text:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch in units:
            # 「十」前面没数字时按 1 算（「十一」= 11）
            total += (current or 1) * units[ch]
            current = 0
        else:
            return None
    return total + current or None


def wanted_chapters(query_text: str) -> list[int]:
    """从问题里认出用户点名要的章节号。

    为什么要这个：向量模型对「第四章」这种小序号并不敏感 —— 实测问
    「第四章讲了什么？」，最相似的居然是第十四章。但用户点名某一章时意图很明确，
    不该交给模糊的向量相似度去猜，所以这里做一次确定性识别。

    返回章号列表（「第三、四章」这种多章写法目前只认第一个）。
    """
    found: list[int] = []
    for m in re.finditer(r"第\s*([0-9零一二三四五六七八九十百两]{1,6})\s*[章节回]", query_text):
        num = _number_in(m.group(1))
        if num and num not in found:
            found.append(num)
    return found


def retrieve(
    book_id: int,
    query_text: str,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = MAX_DISTANCE,
) -> list[dict]:
    """公开检索入口（路由层用）。

    如果用户明确点名了某一章（「第四章讲了什么」），就优先返回该章的内容，
    否则走常规的向量相似度检索。
    """
    chapters = wanted_chapters(query_text)
    if chapters:
        picked = _retrieve_chapters(book_id, chapters, top_k)
        if picked:
            return picked
    return _retrieve(book_id, query_text, top_k, max_distance)


# 从章节标题里抓出「第X章/节/回」的 X
_TITLE_NUM_RE = re.compile(r"第\s*([0-9零一二三四五六七八九十百两]{1,6})\s*[章节回]")


def _title_number(title: str) -> int | None:
    """从章节标题里解析出它自带的章号。如「第四章 悬赏」→ 4，「卷首」→ None。

    注意不能用 chapter_index 去对：那个序号是解析时按顺序编的（「卷首」也占了一号），
    和书里印的章号会错开一位。用户说「第四章」指的是书上的编号，所以必须从标题里取。
    """
    m = _TITLE_NUM_RE.search(title)
    if not m:
        return None
    return _number_in(m.group(1))


def _retrieve_chapters(book_id: int, chapters: list[int], limit: int) -> list[dict]:
    """取用户点名的那几章。

    先用标题里的章号找到对应的 chapter_index，再按它过滤取块。
    """
    col = collection(book_id)
    if col is None:
        return []

    # 取出所有块的元数据，建立「书上印的章号 → chapter_index」映射。
    # 只取 metadatas（不含 documents），几百条的开销可以接受；
    # 顺带按 chapter_index 去重，一本书通常只有几十章。
    try:
        got = col.get(include=["metadatas"])
    except Exception:
        return []

    number_to_index: dict[int, int] = {}
    for meta in got.get("metadatas") or []:
        index = int(meta.get("chapter_index", 0))
        if index in number_to_index.values():
            continue
        num = _title_number(str(meta.get("chapter_title", "")))
        if num is not None:
            number_to_index.setdefault(num, index)

    wanted_indexes = [number_to_index[n] for n in chapters if n in number_to_index]
    if not wanted_indexes:
        return []

    per_chapter = max(1, limit // len(wanted_indexes))
    results: list[dict] = []
    for index in wanted_indexes:
        try:
            part = col.get(
                where={"chapter_index": index},
                include=["documents", "metadatas"],
            )
        except Exception:
            continue

        rows = []
        for doc, meta in zip(part.get("documents") or [], part.get("metadatas") or []):
            rows.append(
                {
                    "text": doc,
                    "distance": 0.0,   # 点名命中，不参与相似度比较
                    "chapter_index": int(meta.get("chapter_index", 0)),
                    "chapter_title": meta.get("chapter_title", ""),
                    "page": int(meta.get("page", 1)),
                    "start_char": int(meta.get("start_char", 0)),
                    "end_char": int(meta.get("end_char", 0)),
                }
            )
        # 取该章最靠前的几块（按页码排序 = 按正文顺序）
        rows.sort(key=lambda r: r["page"])
        results.extend(rows[:per_chapter])

    return results[:limit]
