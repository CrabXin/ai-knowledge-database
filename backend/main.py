"""FastAPI 应用入口，聚合所有接口路由。

接口分组：
- /api/login, /api/me          登录与当前用户
- /api/crawl/*                 数据采集（启动需管理员）与状态轮询
- /api/dates, /api/data        采集日期列表、数据预览（按日期）
- /api/analysis/*              统计 / 聚类 / 关联规则 / 爆款预测
- /api/ai/*                    AI 知识库问答与引擎状态
启动时初始化默认用户并开启每日定时采集。
"""
import os
import threading

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analysis
import ai_qa
import auth
import config
import db_store
import scheduler
import storage

app = FastAPI(title="B站数据分析与AI知识库系统", version="1.0")

# 开发期允许跨域（前端 Vite dev server）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    auth.init_default_users()
    scheduler.start_scheduler()
    # 启动时后台对齐 CSV→MongoDB/Redis，自动修复服务/Redis 重启丢数或采集漏写导致的不同步。
    # 放后台守护线程执行，不阻塞 Web 服务启动。
    threading.Thread(target=_sync_storage_on_startup, daemon=True).start()


def _sync_storage_on_startup():
    """启动时以 CSV 主存储为准回填 Mongo/Redis，并打印结果。失败不影响服务运行。"""
    try:
        res = db_store.sync_from_csv()
        print(f"[startup] 存储同步完成：{res}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[startup] 存储同步跳过（失败）：{e}", flush=True)


# ---------------- 请求体模型 ----------------

class LoginReq(BaseModel):
    username: str
    password: str


class CrawlReq(BaseModel):
    keyword: str = config.DEFAULT_KEYWORD
    pages: int = config.DEFAULT_PAGES
    delay: float = config.DEFAULT_DELAY
    enrich: bool = config.DEFAULT_ENRICH


class AskReq(BaseModel):
    question: str
    crawl_date: str = None
    session_id: str = None  # 前端生成的会话标识，带上则启用多轮上下文记忆


class ResetReq(BaseModel):
    session_id: str


class CreateUserReq(BaseModel):
    username: str
    password: str
    role: str = "user"  # user | admin（admin 仅超级用户可建）


# ---------------- 登录鉴权 ----------------

@app.post("/api/login")
def login(req: LoginReq):
    user = auth.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_token(user["username"], user["role"])
    return {"token": token, "username": user["username"], "role": user["role"]}


@app.get("/api/me")
def me(user: dict = Depends(auth.get_current_user)):
    return user


# ---------------- 用户管理（管理员 / 超级用户）----------------

@app.get("/api/users")
def list_users(user: dict = Depends(auth.require_user_manager)):
    """列出所有用户，并返回当前账号可创建的角色列表。"""
    if user["role"] == auth.ROLE_SUPERADMIN:
        creatable = [auth.ROLE_ADMIN, auth.ROLE_USER]
    else:
        creatable = [auth.ROLE_USER]
    return {"users": auth.list_users(), "creatable_roles": creatable, "my_role": user["role"]}


@app.post("/api/users")
def create_user(req: CreateUserReq, user: dict = Depends(auth.require_user_manager)):
    """新增账号：管理员可建普通用户，超级用户可建管理员/普通用户。"""
    if not auth.can_create_role(user["role"], req.role):
        raise HTTPException(status_code=403, detail="无权创建该角色账号")
    try:
        created = auth.create_user(req.username, req.password, req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "账号创建成功，可直接登录", "user": created}


# ---------------- 数据采集 ----------------

@app.get("/api/crawl/status")
def crawl_status(user: dict = Depends(auth.get_current_user)):
    return storage.read_status()


@app.post("/api/crawl/start")
def crawl_start(req: CrawlReq, user: dict = Depends(auth.require_admin)):
    """启动一次手动采集（仅管理员）。后台执行，立即返回。"""
    ok = scheduler.run_crawl_async(req.keyword, req.pages, req.delay, req.enrich)
    if not ok:
        raise HTTPException(status_code=409, detail="已有采集任务正在运行，请稍候")
    return {"message": "采集任务已启动，可通过状态接口查看进度", "started": True}


# ---------------- 数据查看 ----------------

@app.get("/api/dates")
def dates(user: dict = Depends(auth.get_current_user)):
    return {"dates": storage.list_crawl_dates()}


@app.get("/api/storage/status")
def storage_status(user: dict = Depends(auth.get_current_user)):
    """返回各存储系统（MongoDB / Redis）的连接状态与数据量。"""
    return db_store.storage_status()


@app.post("/api/storage/sync")
def storage_sync(user: dict = Depends(auth.require_admin)):
    """以 CSV 主存储为准，将全部数据回填到 MongoDB / Redis，修复三方计数不同步（仅管理员）。"""
    return db_store.sync_from_csv()


@app.get("/api/data")
def data(crawl_date: str = None, limit: int = 50,
         user: dict = Depends(auth.get_current_user)):
    """返回数据预览（默认前 50 条，按播放量降序）。"""
    df = storage.load_videos(crawl_date)
    if df.empty:
        return {"total": 0, "rows": []}
    df = df.sort_values("play", ascending=False).head(limit)
    return {"total": int(len(storage.load_videos(crawl_date))), "rows": df.to_dict(orient="records")}


# ---------------- 数据分析 ----------------

@app.get("/api/analysis/statistics")
def api_statistics(crawl_date: str = None, user: dict = Depends(auth.get_current_user)):
    return analysis.statistics(crawl_date)


@app.get("/api/analysis/clustering")
def api_clustering(crawl_date: str = None, k: int = 3,
                   user: dict = Depends(auth.get_current_user)):
    return analysis.clustering(crawl_date, k)


@app.get("/api/analysis/association")
def api_association(crawl_date: str = None, user: dict = Depends(auth.get_current_user)):
    return analysis.association_rules(crawl_date)


@app.get("/api/analysis/prediction")
def api_prediction(crawl_date: str = None, user: dict = Depends(auth.get_current_user)):
    return analysis.hot_prediction(crawl_date)


@app.get("/api/analysis/spark")
def api_spark(crawl_date: str = None, user: dict = Depends(auth.get_current_user)):
    """模块五：Spark 分布式分析（首次调用需启动 Spark，约十几秒）。"""
    import spark_analysis  # 懒加载，避免拖慢服务启动
    return spark_analysis.spark_analyze(crawl_date)


# ---------------- AI 问答 ----------------

@app.get("/api/ai/status")
def ai_status(user: dict = Depends(auth.get_current_user)):
    model = ai_qa._pick_ollama_model()
    return {"engine": f"ollama:{model}" if model else "rule",
            "ollama_available": model is not None}


@app.post("/api/ai/ask")
def ai_ask(req: AskReq, user: dict = Depends(auth.get_current_user)):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    return ai_qa.answer(req.question, req.crawl_date, req.session_id)


@app.post("/api/ai/reset")
def ai_reset(req: ResetReq, user: dict = Depends(auth.get_current_user)):
    """清空指定会话的多轮上下文（用户点"清空对话"时调用）。"""
    ai_qa.reset_history(req.session_id)
    return {"ok": True}


# ---------------- 生产环境静态托管（前端打包后）----------------

_dist = os.path.join(config.BASE_DIR, "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="static")
