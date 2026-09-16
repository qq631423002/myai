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

# Session 中间件密钥
secret_key = os.getenv("SECRET_KEY", "change-me-随机字符串")
