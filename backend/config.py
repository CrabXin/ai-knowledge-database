"""全局配置模块。

集中管理路径、CSV 字段、爬虫与 AI 相关的默认参数，便于各模块统一引用。
所有路径均以 backend 目录为基准，保证在任意工作目录下启动都能正确定位。
"""
import os

# ---- 基础路径 ----
# 当前文件所在目录即 backend 根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 数据存储目录（CSV、用户表等）
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 采集结果统一存放的主 CSV 文件（按需求"存到一个csv文件"）
VIDEO_CSV = os.path.join(DATA_DIR, "videos.csv")
# 用户账号表（含角色）
USER_CSV = os.path.join(DATA_DIR, "users.csv")
# 采集任务状态文件（供前端轮询进度，实现"持续更新"展示）
CRAWL_STATUS_FILE = os.path.join(DATA_DIR, "crawl_status.json")

# ---- CSV 字段定义（与数据解析文档保持一致）----
# 每个字段含义详见 docs/数据字段解析文档.md
VIDEO_COLUMNS = [
    "bvid",         # 视频唯一标识（B站BV号）
    "title",        # 视频标题
    "url",          # 视频链接
    "author",       # UP主（博主）昵称
    "mid",          # UP主用户ID
    "play",         # 播放量
    "danmaku",      # 弹幕数
    "reply",        # 评论数
    "favorite",     # 收藏数
    "coin",         # 投币数
    "share",        # 转发（分享）数
    "like",         # 点赞数
    "duration",     # 时长（秒）
    "pubdate",      # 视频发布时间（yyyy-mm-dd HH:MM:SS）
    "keyword",      # 采集时使用的搜索关键词
    "crawl_date",   # 采集日期（yyyy-mm-dd），用于按日期查看
]

# ---- 鉴权配置 ----
JWT_SECRET = os.environ.get("JWT_SECRET", "ai-knowledge-base-secret-key-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# ---- 爬虫默认参数 ----
DEFAULT_KEYWORD = "大数据技术"     # 默认搜索关键词
DEFAULT_PAGES = 3                  # 默认采集页数（每页约20-42条）
DEFAULT_DELAY = 1.0               # 每次请求间隔（秒），降低被反爬概率
DEFAULT_ENRICH = True             # 是否调用视频详情接口补全点赞/投币/转发
DEFAULT_WORKERS = 6               # 详情补全并发线程数（越大越快，但越易触发反爬）
ENRICH_DELAY = 0.3                # 并发补全时每个线程的礼貌间隔（秒），比 DEFAULT_DELAY 小

# ---- 存储系统配置（模块三：任选2个以上，本项目用 MongoDB + Redis）----
# 是否启用各存储后端（关闭则跳过，不影响系统运行）
ENABLE_MONGO = True
ENABLE_REDIS = True

# MongoDB
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = "bili_kb"            # 数据库名（独立库，不影响你已有的库）
MONGO_COLLECTION = "videos"    # 集合名

# Redis
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = 0

# ---- AI 配置 ----
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
# 优先使用的本地离线模型（按可用性自动回退）
OLLAMA_MODELS = ["qwen2.5:3b", "llama3:8b"]
