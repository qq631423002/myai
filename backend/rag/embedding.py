"""文本向量化（embedding）。

为什么用本地模型而不是调 API：
  DeepSeek 没有公开的 embedding 接口，而本项目现有的 Key 只够调对话模型。
  本地 sentence-transformers 模型（bge-small-zh-v1.5）中文检索效果好、
  只有 512 维、纯 CPU 也能跑，还省一个 API Key。

为什么模型要懒加载：
  Chroma 的 PersistentClient 会保存/序列化 EmbeddingFunction 的配置，
  如果在 __init__ 里就把模型读进内存，每次新建客户端都会重新加载权重（很慢）。
"""
import logging
from functools import lru_cache
from threading import Lock
from typing import Sequence

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

# 注意：HF_ENDPOINT / HF_HUB_* 这些环境变量必须「在任何 transformers、huggingface_hub
# 被导入之前」设好，而 huggingface_hub 的 ENDPOINT 是导入时定死的常量。
# 这里 import common.config 就是为了触发那段设置（它比本模块更早、且优先执行）。
from common.config import embedding_model  # noqa: F401  (导入即完成环境变量设置)

logger = logging.getLogger(__name__)

# 推理时的批大小。32 在纯 CPU 上速度/内存比较均衡（实测约 26 段/秒）。
_BATCH_SIZE = 32

_model_lock = Lock()


def _repo_cache_dir(model_name: str) -> str | None:
    """模型在本地缓存里的快照目录；没缓存过就返回 None。

    为什么要自己找目录，而不是让 SentenceTransformer 去判断：
    它默认每次都会向 Hub 发一次元数据请求（HEAD /model/resolve/main/...），
    国内容器/网络下这个请求会一直超时重试（日志里那串 WinError 10060），
    表现就是「上传后进度永远停在 0%」。既然模型已经下好了，就直接从本地目录加载，
    绕开那次网络请求。
    """
    try:
        from huggingface_hub import snapshot_download

        # local_files_only=True 只查本地，不发网络请求
        return snapshot_download(model_name, local_files_only=True)
    except Exception:
        return None


@lru_cache(maxsize=2)
def get_model(model_name: str):
    """加载并缓存 embedding 模型。同名模型在整个进程里只加载一次。"""
    from sentence_transformers import SentenceTransformer

    with _model_lock:
        local_dir = _repo_cache_dir(model_name)
        if local_dir:
            # 本地已有缓存：local_files_only=True 让它完全不发网络请求
            logger.info("[rag] 从本地缓存加载 embedding 模型：%s", local_dir)
            return SentenceTransformer(model_name, local_files_only=True)

        # 本地没有：需要下载。这里给用户一个明确提示，免得以为程序卡死了
        logger.warning(
            "[rag] 本地没有 embedding 模型 %s，正在下载（约 100MB，首次较慢）…",
            model_name,
        )
        return SentenceTransformer(model_name)


def encode(
    texts: Sequence[str],
    batch_size: int = _BATCH_SIZE,
    model_name: str | None = None,
) -> list[list[float]]:
    """把一批文本转向量。

    normalize_embeddings=True 让向量长度为 1，这样余弦距离就是对内积，
    检索时的相似度更稳定，也方便后面用同一个阈值判断「书里到底有没有相关内容」。
    """
    if not texts:
        return []
    model = get_model(model_name or embedding_model)
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def encode_one(text: str, model_name: str | None = None) -> list[float]:
    """把一段文本转向量（检索时用）。"""
    return encode([text], model_name=model_name)[0]


class LocalEmbeddingFunction(EmbeddingFunction[Documents]):
    """给 Chroma 用的 embedding 函数包装。

    真正干活的是上面缓存的 get_model()，这里只是为了满足 Chroma 的接口。
    """

    def __init__(self, model_name: str | None = None):
        # 只记名字，不加载模型 —— 见模块开头的说明
        self.model_name = model_name or embedding_model

    def __call__(self, input: Documents) -> Embeddings:
        # 用本实例记录的名字，保证「显式换了模型」时行为一致
        return encode(list(input), model_name=self.model_name)

    @staticmethod
    def name() -> str:
        """Chroma 持久化自定义 embedding 函数时用它做标识。"""
        return "local-sentence-transformer"

    def get_config(self) -> dict:
        return {"model_name": self.model_name}

    @classmethod
    def build_from_config(cls, config: dict):
        return cls(config.get("model_name"))
