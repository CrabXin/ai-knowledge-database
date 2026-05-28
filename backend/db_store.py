"""多存储系统写入模块（实训模块三）。

将模块二清洗后的数据，同步写入两个存储系统：
- MongoDB：以文档形式存储每条视频，按 (bvid, crawl_date) upsert，便于灵活查询；
- Redis：以 Hash 存每条视频，并用 Sorted Set 维护按播放量的排行榜、用 Set 维护当日索引，
         便于做 Top-N 等快速查询。

设计原则：任一后端不可用时自动跳过并返回状态，不影响 CSV 主流程与系统运行。
访问本地服务统一绕过系统代理（trust_env 不影响这两个库的客户端，但 Mongo/Redis 走 TCP 不读代理）。
"""
import config

# 数值字段（写入时转 int，便于排序/统计）
_NUM = ["play", "danmaku", "reply", "favorite", "coin", "share", "like", "duration"]


# ---------------- MongoDB ----------------

def _mongo_client():
    import pymongo
    return pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=2000)


def save_to_mongo(df, crawl_date):
    """按 (bvid, crawl_date) upsert 写入 MongoDB，返回写入条数。"""
    client = _mongo_client()
    client.admin.command("ping")  # 触发连接校验，失败抛异常
    col = client[config.MONGO_DB][config.MONGO_COLLECTION]
    # 建立索引（幂等）
    col.create_index([("bvid", 1), ("crawl_date", 1)], unique=True)
    col.create_index([("crawl_date", 1)])
    col.create_index([("play", -1)])

    from pymongo import UpdateOne
    ops = []
    for rec in df.to_dict(orient="records"):
        for k in _NUM:
            if k in rec:
                rec[k] = int(rec[k])
        ops.append(UpdateOne(
            {"bvid": rec["bvid"], "crawl_date": rec["crawl_date"]},
            {"$set": rec}, upsert=True))
    if ops:
        col.bulk_write(ops, ordered=False)
    count = col.count_documents({"crawl_date": crawl_date})
    client.close()
    return count


# ---------------- Redis ----------------

def _redis_client():
    import redis
    return redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT,
                       db=config.REDIS_DB, socket_connect_timeout=2, decode_responses=True)


def save_to_redis(df, crawl_date):
    """写入 Redis：每条视频一个 Hash + 当日索引 Set + 播放量排行 ZSet + 汇总。"""
    r = _redis_client()
    r.ping()
    pipe = r.pipeline()
    total_play = 0
    for rec in df.to_dict(orient="records"):
        bvid = rec["bvid"]
        for k in _NUM:
            if k in rec:
                rec[k] = int(rec[k])
        total_play += rec.get("play", 0)
        # 每条视频存为 Hash
        key = f"video:{crawl_date}:{bvid}"
        pipe.hset(key, mapping={k: ("" if v is None else str(v)) for k, v in rec.items()})
        # 当日 bvid 索引
        pipe.sadd(f"index:{crawl_date}", bvid)
        # 播放量排行榜（ZSet）
        pipe.zadd(f"rank:play:{crawl_date}", {bvid: rec.get("play", 0)})
    # 当日汇总
    pipe.hset(f"summary:{crawl_date}", mapping={
        "video_count": len(df), "total_play": total_play})
    # 记录所有采集日期
    pipe.sadd("crawl_dates", crawl_date)
    pipe.execute()
    count = r.scard(f"index:{crawl_date}")
    r.close()
    return count


# ---------------- 统一入口 ----------------

def save_all(df, crawl_date):
    """把数据写入所有启用的存储后端，返回各后端状态。"""
    result = {}
    if config.ENABLE_MONGO:
        try:
            result["mongodb"] = {"ok": True, "count": save_to_mongo(df, crawl_date)}
        except Exception as e:  # noqa: BLE001
            result["mongodb"] = {"ok": False, "error": str(e)[:120]}
    if config.ENABLE_REDIS:
        try:
            result["redis"] = {"ok": True, "count": save_to_redis(df, crawl_date)}
        except Exception as e:  # noqa: BLE001
            result["redis"] = {"ok": False, "error": str(e)[:120]}
    return result


def sync_from_csv():
    """以 CSV 主存储为准，将全部历史数据回填/重写到 MongoDB 与 Redis，使三方计数一致。

    适用于修复以下不同步场景：
    - 某次采集时 Mongo/Redis 临时不可用，save_all 静默跳过造成的漏写；
    - Redis 未开持久化、重启后内存数据全部丢失。

    写入复用按日期 upsert/覆盖的既有函数，幂等，可安全重复执行。
    返回 CSV 总数与各后端同步后的数据量，便于核对是否一致。
    """
    import storage  # 懒加载，避免模块级循环依赖

    df = storage.load_videos()  # 读取全部日期数据（CSV 为主存储、唯一真值源）
    result = {"csv_total": len(df)}
    if df.empty:
        return result

    # 按采集日期分组，逐日复用既有的按日期写入函数
    groups = [(date, g.reset_index(drop=True)) for date, g in df.groupby("crawl_date")]

    if config.ENABLE_MONGO:
        try:
            for date, g in groups:
                save_to_mongo(g, date)
            client = _mongo_client()
            total = client[config.MONGO_DB][config.MONGO_COLLECTION].count_documents({})
            client.close()
            result["mongodb"] = {"ok": True, "total": total}
        except Exception as e:  # noqa: BLE001
            result["mongodb"] = {"ok": False, "error": str(e)[:120]}

    if config.ENABLE_REDIS:
        try:
            for date, g in groups:
                save_to_redis(g, date)
            r = _redis_client()
            total = len(r.keys("video:*"))
            r.close()
            result["redis"] = {"ok": True, "total": total}
        except Exception as e:  # noqa: BLE001
            result["redis"] = {"ok": False, "error": str(e)[:120]}

    return result


def storage_status():
    """读取各存储后端当前状态与数据量，供前端展示，证明已真实连接。"""
    status = {}
    # MongoDB
    if config.ENABLE_MONGO:
        try:
            client = _mongo_client()
            ver = client.server_info()["version"]
            col = client[config.MONGO_DB][config.MONGO_COLLECTION]
            status["mongodb"] = {"connected": True, "version": ver,
                                 "total_docs": col.count_documents({})}
            client.close()
        except Exception as e:  # noqa: BLE001
            status["mongodb"] = {"connected": False, "error": str(e)[:120]}
    # Redis
    if config.ENABLE_REDIS:
        try:
            r = _redis_client()
            r.ping()
            status["redis"] = {"connected": True,
                               "version": r.info("server")["redis_version"],
                               "total_videos": len(r.keys("video:*"))}
            r.close()
        except Exception as e:  # noqa: BLE001
            status["redis"] = {"connected": False, "error": str(e)[:120]}
    return status
