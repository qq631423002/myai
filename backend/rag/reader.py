"""读取用户上传的书籍，并解析章节与页码信息。

当前版本只支持 TXT 和 Markdown：
  - TXT 是最通用的书本格式，把整本书导出成 txt 就能直接上传。
  - Markdown 方便后续上传笔记、文档。

章节不是靠 AI 猜的，而是用书本身的排版结构识别（「第一章」「Chapter 2」这类）。
好处是：页码定位、章节导读都不需要额外调用模型，也不会给没有章节结构的书硬造章节。
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

# 一页按多少字估算。中文电子书一页大致 900~1100 字，取 1000。
# 注意：这是「估算页」，不是 PDF 的真实页码 —— txt 里本来就没有分页信息。
CHARS_PER_PAGE = 1000

# 章节正文少于这么多字就不单独算一章（多用于滤掉目录页残留、只有标题的空章节）
MIN_CHAPTER_CHARS = 20

# 「强」章节标记：一看就是章节标题的写法。
_STRONG_HEAD_RE = re.compile(
    r"^\s*(?:"
    r"第\s*[零一二三四五六七八九十百千万两0-9]+\s*[章节卷部篇回]"   # 第一章 / 第 12 节
    r"|(?:序章|序言|自序|楔子|引子|尾声|后记|跋|附录|前言|终章)"
    r"|[Cc]hapter\s+[0-9IVXLC]+"
    r"|CHAPTER\s+[0-9IVXLC]+"
    r")"
)

# 「弱」章节标记：编号列表式（1、xxx / §3 xxx）。
# 这类写法在正文里也常见（比如书里的要点列表），所以额外加了两道限制：
# 行必须很短、且不能以句末标点结尾，尽量避免把正文当成章节。
_WEAK_HEAD_RE = re.compile(r"^\s*(?:[0-9]{1,4}\s*[、.．]|§\s*[0-9]{1,4})\s*\S")

# 以这些标点结尾的行是正文，不是标题
_SENTENCE_END = "。！？；，,.;:!?"

# 切块器：优先在段落、换行、中文句号处切，块内保留 120 字重叠，
# 避免「答案正好被切在两块中间」导致检索不到。
# add_start_index=True 让每块带上在全文里的字符起点 —— 页码定位全靠它。
_CHUNK_OVERLAP = 120

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=900,
    chunk_overlap=_CHUNK_OVERLAP,
    add_start_index=True,
    separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
)


@dataclass
class Chapter:
    """书里的一个章节。"""

    index: int          # 从 1 开始的序号
    title: str
    content: str
    start_char: int     # 在全书里的字符起点（页码按它换算）
    end_char: int

    @property
    def start_page(self) -> int:
        return char_to_page(self.start_char)

    @property
    def end_page(self) -> int:
        return char_to_page(max(self.end_char - 1, self.start_char))

    @property
    def char_count(self) -> int:
        return self.end_char - self.start_char


@dataclass
class ParsedBook:
    """解析结果。"""

    title: str
    full_text: str
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return len(self.full_text)

    @property
    def total_pages(self) -> int:
        return char_to_page(max(self.total_chars - 1, 0))

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)


def char_to_page(offset: int) -> int:
    """字符偏移 → 页码（从 1 开始）。"""
    return max(1, offset // CHARS_PER_PAGE + 1)


def _decode(data: bytes) -> str:
    """把上传的文件字节解码成字符串。

    中文 txt 的编码很杂：老书常是 GBK/GB18030，新书多为 UTF-8。
    逐个尝试，全失败才用替换字符兜底（尽量避免让用户什么都读不到）。
    """
    # 带 BOM 的 UTF-8 必须排在 utf-8 前面，否则 \ufeff 会混进正文
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _strip_markdown(text: str) -> str:
    """把 Markdown 语法去掉，只留可读的纯文本。

    只做正则替换，不引 HTML 渲染库：这个功能是「读书」，不是完整的
    Markdown 渲染器，去掉常见标记就够用了。
    """
    text = re.sub(r"^\s*```.*?^\s*```\s*$", "", text, flags=re.S | re.M)  # 代码块
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                       # 图片
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)                   # 链接留文字
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)              # 标题符号
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)                   # 引用
    text = re.sub(r"\*\*|__|~~|`", "", text)                               # 粗体/删除线/行内码
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)                   # 列表符号
    return text


def parse_bytes(filename: str, data: bytes) -> ParsedBook:
    """解析上传的文件。传入文件名（判断格式 + 取书名）和字节内容。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".txt", ".md"):
        raise ValueError("当前只支持 .txt / .md 格式的书")

    text = _decode(data)
    if suffix == ".md":
        text = _strip_markdown(text)

    return _parse_text(text, title=Path(filename).stem)


def _is_chapter_head(line: str) -> bool:
    """判断一行是不是章节标题。"""
    if not line or len(line) > 60:
        return False
    # 以句末标点结尾的基本是正文
    if line[-1] in _SENTENCE_END:
        return False
    if _STRONG_HEAD_RE.match(line):
        return True
    # 弱标记：要求整行很短，否则很可能是正文里的编号列表
    if len(line) <= 24 and _WEAK_HEAD_RE.match(line):
        return True
    return False


def _find_chapter_heads(lines: list[str]) -> list[tuple[str, int]]:
    """扫描出章节标题所在的行。返回 [(标题, 行号)]。"""
    heads: list[tuple[str, int]] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if _is_chapter_head(line):
            heads.append((line, i))
    return heads


def _parse_text(text: str, title: str) -> ParsedBook:
    """把整本书的纯文本切成章节。"""
    if not text.strip():
        raise ValueError("文件内容为空，没有可读的文字")

    # 统一换行符：避免 \r\n 让后面按字符偏移定位时算错
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    heads = _find_chapter_heads(lines)
    # 很多 txt 完全没有章节标记（整本是一大段）。这时当作单章「全文」，
    # 检索照样能用，只是没有章节这个维度。
    if not heads:
        return ParsedBook(
            title=title, full_text=text, chapters=[_make_chapter(1, "全文", text, 0)]
        )

    spans: list[tuple[str, int, int]] = []  # (标题, 正文字符起点, 正文字符终点)

    # 第一个章节标记之前的内容（书名、作者、简介）也算一章，否则会被丢掉
    if heads[0][1] > 0:
        preface = "\n".join(lines[: heads[0][1]]).strip()
        if len(preface) >= MIN_CHAPTER_CHARS:
            start = text.find(preface)
            spans.append(("卷首", max(start, 0), max(start, 0) + len(preface)))

    for n, (head, line_no) in enumerate(heads):
        end_line = heads[n + 1][1] if n + 1 < len(heads) else len(lines)
        body = "\n".join(lines[line_no + 1 : end_line]).strip()
        if len(body) < MIN_CHAPTER_CHARS:
            # 太短的多半是目录页残留或空章节，跳过（避免污染检索结果）
            continue
        # 从标题之后的区域开始找正文，避免标题文字在别处先出现导致定位错位
        head_at = text.find(head)
        search_from = head_at + len(head) if head_at >= 0 else 0
        found = text.find(body, search_from)
        start = found if found >= 0 else search_from
        spans.append((head, start, start + len(body)))

    if not spans:
        return ParsedBook(
            title=title, full_text=text, chapters=[_make_chapter(1, "全文", text, 0)]
        )

    chapters = [
        _make_chapter(i + 1, head, text[s:e], s) for i, (head, s, e) in enumerate(spans)
    ]
    return ParsedBook(title=title, full_text=text, chapters=chapters)


def _make_chapter(index: int, title: str, content: str, start_char: int) -> Chapter:
    return Chapter(
        index=index,
        title=title,
        content=content,
        start_char=start_char,
        end_char=start_char + len(content),
    )


def split_chunks(book: ParsedBook) -> list[dict]:
    """把整本书切成检索块，每块带上所属章节和页码。

    返回的每项：
      text / start_char / end_char / page / chapter_index / chapter_title
    """
    if not book.full_text.strip():
        return []

    # create_documents + add_start_index 能拿到每块在全文里的准确字符起点，
    # 页码定位就靠它。
    docs = _splitter.create_documents([book.full_text])

    chunks: list[dict] = []
    cursor = 0
    for doc in docs:
        body = doc.page_content
        if not body.strip():
            continue
        if "start_index" in doc.metadata:
            start = int(doc.metadata["start_index"])
        else:
            # 兜底：切分器的 start_index 万一没回填（不同版本行为有差异），
            # 就按顺序在全文里查找。直接取默认值 0 会让所有块都变成第 1 页。
            #
            # 注意要往回退一段再找：相邻块有 chunk_overlap 的重叠，
            # 下一块的真正起点其实在「上一块末尾」之前，从末尾往后找会定位过头。
            from_at = max(0, cursor - _CHUNK_OVERLAP * 2)
            found = book.full_text.find(body, from_at)
            start = found if found >= 0 else cursor
        cursor = start + len(body)
        chapter = _locate_chapter(book, start)
        chunks.append(
            {
                "text": body,
                "start_char": start,
                "end_char": start + len(body),
                "page": char_to_page(start),
                "chapter_index": chapter.index if chapter else 0,
                "chapter_title": chapter.title if chapter else "全文",
            }
        )
    return chunks


def _locate_chapter(book: ParsedBook, offset: int) -> Chapter | None:
    """某个字符位置落在哪一章。"""
    for chap in book.chapters:
        if chap.start_char <= offset < chap.end_char:
            return chap
    # 落在章节之间的空隙（比如标题行）时，归到它前面那一章
    previous = None
    for chap in book.chapters:
        if chap.start_char > offset:
            break
        previous = chap
    return previous
