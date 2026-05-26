"""B站真实数据采集模块（实训模块一）。

采集流程：
1. 访问 B 站主页获取匿名 Cookie（buvid 等），降低被反爬概率；
2. 调用 nav 接口获取 WBI 签名所需的 img_key / sub_key；
3. 调用 WBI 版搜索接口按关键词分页采集视频列表（标题、URL、播放量、UP主、弹幕、评论、收藏等）；
4. 对每条视频调用视频详情接口补全 点赞 / 投币 / 转发(分享) 等统计；
5. 清洗（万→数字）后增量写入 CSV，支持持续更新。

注意：B 站搜索接口需要 WBI 签名（w_rid），本模块完整实现该签名算法。
"""
import concurrent.futures
import functools
import hashlib
import threading
import time
import urllib.parse
from datetime import datetime

import pandas as pd
import requests

import cleaner
import config
import db_store
import storage

# WBI 签名用的固定混淆位表（来自 B 站 Web 端逆向，属公开算法）
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
}

SEARCH_API = "https://api.bilibili.com/x/web-interface/wbi/search/type"
NAV_API = "https://api.bilibili.com/x/web-interface/nav"
VIEW_API = "https://api.bilibili.com/x/web-interface/view"


# ---------------- WBI 签名实现 ----------------

def _get_mixin_key(orig: str) -> str:
    """按混淆位表重排 img_key+sub_key，取前 32 位得到 mixin_key。"""
    return functools.reduce(lambda s, i: s + orig[i], _MIXIN_KEY_ENC_TAB, "")[:32]


def _enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """对请求参数进行 WBI 签名，返回带 wts 与 w_rid 的新参数字典。"""
    mixin_key = _get_mixin_key(img_key + sub_key)
    params = dict(params)
    params["wts"] = int(time.time())
    # 按 key 升序排列
    params = dict(sorted(params.items()))
    # 过滤 value 中的 !'()* 字符（B 站要求）
    params = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def _fetch_wbi_keys(session: requests.Session) -> tuple:
    """从 nav 接口获取 WBI 的 img_key 与 sub_key。"""
    resp = session.get(NAV_API, headers=_HEADERS, timeout=10)
    data = resp.json()["data"]["wbi_img"]
    img_key = data["img_url"].rsplit("/", 1)[1].split(".")[0]
    sub_key = data["sub_url"].rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key


# ---------------- 采集主流程 ----------------

def _new_session() -> requests.Session:
    """创建带匿名 Cookie 的会话。"""
    session = requests.Session()
    # 访问主页以获取 buvid 等匿名 Cookie
    try:
        session.get("https://www.bilibili.com", headers=_HEADERS, timeout=10)
    except requests.RequestException:
        pass
    return session


def _duration_to_seconds(text) -> int:
    """把搜索接口返回的 "MM:SS" 或 "HH:MM:SS" 时长转为秒。"""
    if text is None:
        return 0
    parts = str(text).split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return 0
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def _enrich_stats(session: requests.Session, bvid: str, delay: float) -> dict:
    """调用视频详情接口补全 点赞/投币/转发 等统计。失败时返回空字典。"""
    try:
        resp = session.get(VIEW_API, params={"bvid": bvid}, headers=_HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            return {}
        stat = data["data"]["stat"]
        time.sleep(delay)
        return {
            "play": stat.get("view", 0),
            "danmaku": stat.get("danmaku", 0),
            "reply": stat.get("reply", 0),
            "favorite": stat.get("favorite", 0),
            "coin": stat.get("coin", 0),
            "share": stat.get("share", 0),
            "like": stat.get("like", 0),
        }
    except (requests.RequestException, KeyError, ValueError):
        return {}


def crawl(keyword: str = None, pages: int = None, delay: float = None,
          enrich: bool = None, crawl_date: str = None, workers: int = None) -> dict:
    """执行一次采集并写入 CSV。

    Args:
        keyword: 搜索关键词，默认 config.DEFAULT_KEYWORD。
        pages:   采集页数，每页约 20-42 条。
        delay:   每次请求间隔秒数，防止触发反爬。
        enrich:  是否调用详情接口补全点赞/投币/转发。
        crawl_date: 采集日期标记，默认今天。
        workers: 详情补全的并发线程数，默认 config.DEFAULT_WORKERS。

    Returns:
        {"success": bool, "fetched": int, "total": int, "message": str, "crawl_date": str}
    """
    keyword = keyword or config.DEFAULT_KEYWORD
    pages = pages or config.DEFAULT_PAGES
    delay = config.DEFAULT_DELAY if delay is None else delay
    enrich = config.DEFAULT_ENRICH if enrich is None else enrich
    workers = workers or config.DEFAULT_WORKERS
    crawl_date = crawl_date or datetime.now().strftime("%Y-%m-%d")

    storage.write_status({
        "running": True, "message": f"正在采集关键词「{keyword}」...",
        "fetched": 0, "total": 0, "keyword": keyword,
    })

    session = _new_session()
    try:
        img_key, sub_key = _fetch_wbi_keys(session)
    except Exception as e:  # noqa: BLE001 - 网络/结构异常统一兜底
        msg = f"获取 WBI 签名失败：{e}"
        storage.write_status({"running": False, "message": msg, "fetched": 0, "total": 0})
        return {"success": False, "fetched": 0, "total": 0, "message": msg, "crawl_date": crawl_date}

    rows = []
    for page in range(1, pages + 1):
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "page_size": 42,
        }
        signed = _enc_wbi(params, img_key, sub_key)
        try:
            resp = session.get(SEARCH_API, params=signed, headers=_HEADERS, timeout=15)
            payload = resp.json()
        except (requests.RequestException, ValueError) as e:
            storage.write_status({
                "running": True,
                "message": f"第 {page} 页请求异常：{e}，继续后续页",
                "fetched": len(rows), "total": 0,
            })
            time.sleep(delay)
            continue

        if payload.get("code") != 0:
            # 常见 code: -412 触发风控，-110001 等
            storage.write_status({
                "running": True,
                "message": f"第 {page} 页返回 code={payload.get('code')} {payload.get('message','')}",
                "fetched": len(rows), "total": 0,
            })
            time.sleep(delay)
            continue

        results = payload.get("data", {}).get("result", []) or []
        for item in results:
            bvid = item.get("bvid", "")
            if not bvid:
                continue
            row = {
                "bvid": bvid,
                "title": item.get("title", ""),
                "url": f"https://www.bilibili.com/video/{bvid}",
                "author": item.get("author", ""),
                "mid": item.get("mid", ""),
                "play": item.get("play", 0),
                "danmaku": item.get("video_review", 0),
                "reply": item.get("review", 0),
                "favorite": item.get("favorites", 0),
                "coin": 0,
                "share": 0,
                "like": 0,
                "duration": _duration_to_seconds(item.get("duration", "0")),
                "pubdate": datetime.fromtimestamp(item.get("pubdate", 0)).strftime("%Y-%m-%d %H:%M:%S")
                if item.get("pubdate") else "",
                "keyword": keyword,
                "crawl_date": crawl_date,
            }
            rows.append(row)

        storage.write_status({
            "running": True,
            "message": f"已采集第 {page}/{pages} 页，累计 {len(rows)} 条",
            "fetched": len(rows), "total": 0, "keyword": keyword,
        })
        time.sleep(delay)

    # 详情补全：瓶颈在这里（每条视频一个请求），用线程池并发显著加速。
    # 并发会提高被反爬概率，故限制线程数（workers）并保留小幅礼貌间隔（ENRICH_DELAY）。
    # 说明：requests.Session 在多线程下共享做 GET 是常见且可用的（底层连接池线程安全）。
    if enrich and rows:
        enrich_delay = min(delay, config.ENRICH_DELAY)
        total_rows = len(rows)
        done = 0
        lock = threading.Lock()

        def _fill(row):
            stats = _enrich_stats(session, row["bvid"], enrich_delay)
            if stats:
                row.update(stats)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fill, r) for r in rows]
            for _ in concurrent.futures.as_completed(futures):
                with lock:
                    done += 1
                    cur = done
                if cur % 10 == 0 or cur == total_rows:
                    storage.write_status({
                        "running": True,
                        "message": f"正在补全详情 {cur}/{total_rows} 条（{workers} 线程并发）...",
                        "fetched": total_rows, "total": 0, "keyword": keyword,
                    })

    if not rows:
        msg = "未采集到数据（可能触发风控或关键词无结果），请稍后重试或调整关键词"
        storage.write_status({"running": False, "message": msg, "fetched": 0, "total": 0})
        return {"success": False, "fetched": 0, "total": 0, "message": msg, "crawl_date": crawl_date}

    df = pd.DataFrame(rows)
    df = cleaner.clean_dataframe(df)            # 模块二：清洗
    total = storage.save_videos(df)             # 主存储：CSV

    # 模块三：将清洗后的数据同步写入 MongoDB + Redis
    db_result = db_store.save_all(df, crawl_date)
    db_summary = "，".join(
        f"{name}:{'成功' if r.get('ok') else '失败'}" for name, r in db_result.items()
    )

    msg = f"采集完成，本次 {len(rows)} 条，库内累计 {total} 条" + (f"；存储[{db_summary}]" if db_summary else "")
    storage.write_status({
        "running": False, "message": msg,
        "fetched": len(rows), "total": total, "keyword": keyword,
        "db_result": db_result,
    })
    return {"success": True, "fetched": len(rows), "total": total,
            "message": msg, "crawl_date": crawl_date, "db_result": db_result}
