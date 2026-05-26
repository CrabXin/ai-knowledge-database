"""Spark 分布式分析模块（实训模块五）。

使用本地 SparkSession（local[*]）对清洗后的数据做分布式分析，至少包含 4 种：
  1. UP主视频数 Top10（Spark SQL GROUP BY）
  2. 播放量整体统计（min/max/avg/sum/stddev，DataFrame agg）
  3. 播放量区间分布（Spark SQL CASE WHEN 分桶）
  4. 各互动指标平均值（DataFrame agg）
  5. 视频时长分桶 vs 平均播放量（Spark SQL，附加第5种）

Windows 适配：绑定 127.0.0.1、指定 PYSPARK_PYTHON、Java17 add-opens，
SparkSession 懒加载且全局复用（首次调用约需十几秒启动）。
Spark 不可用时自动回退到 pandas 等价实现，保证接口始终返回。
"""
import os
import sys
import threading

import storage

# 必须在 pyspark 启动前设置
os.environ.setdefault("JAVA_HOME", "E:/JDK17")
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

_spark = None
_lock = threading.Lock()

_ADD_OPENS = (
    "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED "
    "--add-opens=java.base/java.nio=ALL-UNNAMED "
    "--add-opens=java.base/java.lang=ALL-UNNAMED "
    "--add-opens=java.base/java.util=ALL-UNNAMED"
)


def get_spark():
    """懒加载并复用全局 SparkSession。"""
    global _spark
    with _lock:
        if _spark is None:
            from pyspark.sql import SparkSession
            _spark = (SparkSession.builder
                      .master("local[*]").appName("BiliKB-SparkAnalysis")
                      .config("spark.driver.host", "127.0.0.1")
                      .config("spark.driver.bindAddress", "127.0.0.1")
                      .config("spark.ui.enabled", "false")
                      .config("spark.driver.extraJavaOptions", _ADD_OPENS)
                      .config("spark.executor.extraJavaOptions", _ADD_OPENS)
                      .config("spark.sql.execution.arrow.pyspark.enabled", "true")
                      .config("spark.sql.shuffle.partitions", "4")
                      .getOrCreate())
            _spark.sparkContext.setLogLevel("ERROR")
        return _spark


_FEATS = ["play", "like", "coin", "favorite", "share", "danmaku", "reply", "duration"]


def _run_spark(df_pd):
    """在 Spark 上执行 5 种分布式分析，返回结果字典。"""
    from pyspark.sql import functions as F

    spark = get_spark()
    cols = ["author"] + _FEATS
    pdf = df_pd[cols].copy()
    pdf["author"] = pdf["author"].fillna("").astype(str)
    for c in _FEATS:
        pdf[c] = pdf[c].fillna(0).astype("int64")

    sdf = spark.createDataFrame(pdf)
    sdf.createOrReplaceTempView("videos")

    # 1. UP主视频数 Top10（Spark SQL）
    top_authors = spark.sql(
        "SELECT author, COUNT(*) AS n FROM videos GROUP BY author ORDER BY n DESC LIMIT 10"
    ).collect()

    # 2. 播放量整体统计（DataFrame agg）
    s = sdf.agg(
        F.min("play").alias("min"), F.max("play").alias("max"),
        F.round(F.avg("play")).alias("avg"), F.sum("play").alias("sum"),
        F.round(F.stddev("play")).alias("std"),
    ).collect()[0]

    # 3. 播放量区间分布（Spark SQL CASE WHEN 分桶）
    dist = spark.sql("""
        SELECT bucket, COUNT(*) AS n FROM (
          SELECT CASE
            WHEN play < 10000 THEN '<1万'
            WHEN play < 100000 THEN '1万-10万'
            WHEN play < 500000 THEN '10万-50万'
            WHEN play < 1000000 THEN '50万-100万'
            ELSE '>100万' END AS bucket
          FROM videos)
        GROUP BY bucket
    """).collect()

    # 4. 各互动指标平均值（DataFrame agg）
    inter_cols = ["like", "coin", "favorite", "share", "danmaku", "reply"]
    inter = sdf.agg(*[F.round(F.avg(c)).alias(c) for c in inter_cols]).collect()[0]

    # 5. 时长分桶 vs 平均播放量（Spark SQL）
    durbk = spark.sql("""
        SELECT dur, ROUND(AVG(play)) AS avg_play, COUNT(*) AS n FROM (
          SELECT play, CASE
            WHEN duration < 300 THEN '<5分钟'
            WHEN duration < 900 THEN '5-15分钟'
            WHEN duration < 1800 THEN '15-30分钟'
            ELSE '>30分钟' END AS dur
          FROM videos)
        GROUP BY dur
    """).collect()

    return {
        "empty": False,
        "engine": f"Spark {spark.version}（分布式）",
        "top_authors": [{"author": r["author"], "count": int(r["n"])} for r in top_authors],
        "play_stats": {"min": int(s["min"]), "max": int(s["max"]),
                       "avg": int(s["avg"] or 0), "sum": int(s["sum"]),
                       "std": int(s["std"] or 0)},
        "play_distribution": [{"name": r["bucket"], "value": int(r["n"])} for r in dist],
        "avg_interactions": {c: int(inter[c] or 0) for c in inter_cols},
        "duration_vs_play": [{"dur": r["dur"], "avg_play": int(r["avg_play"] or 0),
                              "count": int(r["n"])} for r in durbk],
    }


def _run_pandas(df_pd, error=None):
    """Spark 不可用时的 pandas 等价兜底。"""
    ta = df_pd.groupby("author").size().sort_values(ascending=False).head(10)
    import pandas as pd
    bins = [0, 10000, 100000, 500000, 1000000, float("inf")]
    labels = ["<1万", "1万-10万", "10万-50万", "50万-100万", ">100万"]
    dist = pd.cut(df_pd["play"], bins=bins, labels=labels, right=False).value_counts()
    dbins = [0, 300, 900, 1800, float("inf")]
    dlabels = ["<5分钟", "5-15分钟", "15-30分钟", ">30分钟"]
    dgrp = df_pd.assign(dur=pd.cut(df_pd["duration"], bins=dbins, labels=dlabels, right=False))
    durbk = dgrp.groupby("dur", observed=True)["play"].agg(["mean", "count"])
    inter_cols = ["like", "coin", "favorite", "share", "danmaku", "reply"]
    return {
        "empty": False,
        "engine": "pandas（Spark不可用时的等价兜底）",
        "fallback_reason": (error or "")[:160],
        "top_authors": [{"author": a, "count": int(c)} for a, c in ta.items()],
        "play_stats": {"min": int(df_pd["play"].min()), "max": int(df_pd["play"].max()),
                       "avg": int(df_pd["play"].mean()), "sum": int(df_pd["play"].sum()),
                       "std": int(df_pd["play"].std() or 0)},
        "play_distribution": [{"name": str(k), "value": int(v)} for k, v in dist.items()],
        "avg_interactions": {c: int(df_pd[c].mean()) for c in inter_cols},
        "duration_vs_play": [{"dur": str(idx), "avg_play": int(row["mean"]),
                              "count": int(row["count"])} for idx, row in durbk.iterrows()],
    }


def spark_analyze(crawl_date=None):
    """对外入口：优先 Spark 分布式分析，失败回退 pandas。"""
    df_pd = storage.load_videos(crawl_date)
    if df_pd.empty:
        return {"empty": True, "message": "暂无数据，请先采集"}
    try:
        return _run_spark(df_pd)
    except Exception as e:  # noqa: BLE001
        return _run_pandas(df_pd, error=str(e))
