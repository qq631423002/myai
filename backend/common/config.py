"""全局配置：从 .env 读取环境变量。"""
import os

from dotenv import load_dotenv

# 读取 .env 文件（在 backend 目录下运行即可找到）
load_dotenv()

# DeepSeek API（OpenAI 兼容接口）
# 依次尝试读环境变量 API_KEY、myapikey（你在 Windows 里设的那个）
api_key = os.getenv("API_KEY") or os.getenv("myapikey", "")
api_base_url = os.getenv("API_BASE_URL", "https://api.deepseek.com")
model_name = os.getenv("MODEL_NAME", "deepseek-v4-flash")

# ===== RAG（向量检索）=====
# 把书里的文字转向量用的本地模型。
# 为什么用本地模型：DeepSeek 没有公开的 embedding 接口，做 RAG 必须另找向量化方案。
# bge-small-zh-v1.5 中文检索效果好、只有 512 维、纯 CPU 也能跑（实测约 26 段/秒），
# 而且不用再申请一个 API Key。
embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

# 模型下载源。国内直连 huggingface.co 经常超时，所以默认走镜像；
# 想用官方源就在 .env 里写 HF_ENDPOINT=https://huggingface.co。
hf_endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")

# 【必须在任何 transformers / huggingface_hub 被导入之前设好】
#
# 踩过的坑：huggingface_hub 是在「模块导入时」就把 ENDPOINT 常量写死的
# （见它的 constants.py：ENDPOINT = os.getenv("HF_ENDPOINT", ...)）。
# 而 rag/reader.py 会 import langchain_text_splitters，后者又会 import transformers，
# 于是 huggingface_hub 在 rag/embedding.py 设置环境变量之前就已经加载完了 ——
# 结果镜像配置完全不起作用，模型下载一直去连超时的 huggingface.co。
#
# config.py 被几乎所有模块最先导入，所以把环境变量放在这里设最保险。
os.environ.setdefault("HF_ENDPOINT", hf_endpoint)
# Windows 不支持软链接时的告警，没必要让用户看到
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# transformers 的分词器并发告警
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# 缩短超时：镜像不通时别让用户等几分钟（默认是 10s/10s，这里显式写出来更清楚）
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

# Session 中间件密钥
secret_key = os.getenv("SECRET_KEY", "change-me-随机字符串")
