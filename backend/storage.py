"""CSV 数据存储模块。

负责采集结果的读写、增量去重更新，以及采集状态的持久化。
所有数据统一落地到 config.VIDEO_CSV 这一个 CSV 文件，
通过 crawl_date 字段区分不同采集日期，支持"持续更新"与"按日期查看"。
"""
import json
import os
import threading

import pandas as pd

import config

# 写 CSV 时加锁，避免定时任务与手动采集并发写入导致文件损坏
_csv_lock = threading.Lock()


def load_videos(crawl_date: str = None) -> pd.DataFrame:
    """读取采集数据。

    Args:
        crawl_date: 若指定（yyyy-mm-dd），仅返回该日期采集的数据；否则返回全部。

    Returns:
        DataFrame，列为 config.VIDEO_COLUMNS；文件不存在时返回空表。
    """
    if not os.path.exists(config.VIDEO_CSV):
        return pd.DataFrame(columns=config.VIDEO_COLUMNS)
    df = pd.read_csv(config.VIDEO_CSV, dtype={"bvid": str, "mid": str})
    # 保证数值列为数字类型，便于后续分析
    numeric_cols = ["play", "danmaku", "reply", "favorite", "coin", "share", "like", "duration"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    if crawl_date:
        df = df[df["crawl_date"] == crawl_date].reset_index(drop=True)
    return df


def save_videos(new_df: pd.DataFrame) -> int:
    """增量保存采集数据并去重。

    去重规则：同一 bvid + crawl_date 视为同一条，新数据覆盖旧数据，
    这样同一天多次采集会更新最新统计值，实现"持续更新数据"。

    Args:
        new_df: 本次采集得到的数据（列须包含 config.VIDEO_COLUMNS）。

    Returns:
        合并后 CSV 中的总记录数。
    """
    with _csv_lock:
        # 补齐缺失列，保证列顺序一致
        for col in config.VIDEO_COLUMNS:
            if col not in new_df.columns:
                new_df[col] = ""
        new_df = new_df[config.VIDEO_COLUMNS]

        if os.path.exists(config.VIDEO_CSV):
            old_df = pd.read_csv(config.VIDEO_CSV, dtype={"bvid": str, "mid": str})
            combined = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined = new_df

        # 后出现的（本次采集）保留，drop_duplicates 默认保留 last
        combined = combined.drop_duplicates(subset=["bvid", "crawl_date"], keep="last")
        combined = combined.reset_index(drop=True)
        combined.to_csv(config.VIDEO_CSV, index=False, encoding="utf-8-sig")
        return len(combined)


def list_crawl_dates() -> list:
    """返回 CSV 中已有的所有采集日期，降序排列，供前端日期选择器使用。"""
    df = load_videos()
    if df.empty or "crawl_date" not in df.columns:
        return []
    dates = sorted(df["crawl_date"].dropna().unique().tolist(), reverse=True)
    return dates


# ---------- 采集状态持久化（供前端轮询进度）----------

def read_status() -> dict:
    """读取当前采集状态。"""
    if not os.path.exists(config.CRAWL_STATUS_FILE):
        return {"running": False, "message": "暂无采集任务", "fetched": 0, "total": 0}
    with open(config.CRAWL_STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_status(status: dict) -> None:
    """写入采集状态。"""
    with open(config.CRAWL_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
