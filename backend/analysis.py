"""数据分析、挖掘与可视化数据生成模块（实训模块四 / 五 / 六）。

提供四类能力，输出均为可直接被前端 ECharts 使用的 JSON：
1. 基础统计（模块五 Spark 分析的等价单机实现）：UP主视频数、播放量分布、互动总量等；
2. KMeans 聚类（模块四）：按互动指标把视频聚成若干类；
3. 关联规则挖掘（模块四）：点赞/投币/收藏/转发 等高互动行为之间的关联；
4. 爆款预测（模块四）：用互动特征预测视频是否为高播放"爆款"。

为保证零额外依赖，关联规则采用自实现的 Apriori。
"""
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

import storage

# 参与挖掘的互动指标
_METRICS = ["play", "like", "coin", "favorite", "share", "danmaku", "reply"]


def _load(crawl_date: str = None) -> pd.DataFrame:
    return storage.load_videos(crawl_date)


# ---------------- 1. 基础统计（可视化图 1~4 数据源）----------------

def statistics(crawl_date: str = None) -> dict:
    """汇总统计，返回多个可视化图所需数据。"""
    df = _load(crawl_date)
    if df.empty:
        return {"empty": True}

    # 图1：视频数最多的 UP 主 Top10（柱状图）
    top_authors = (
        df.groupby("author").size().sort_values(ascending=False).head(10)
    )
    top_authors_chart = {
        "names": top_authors.index.tolist(),
        "counts": [int(x) for x in top_authors.values],
    }

    # 图2：播放量最高的视频 Top10（柱状图）
    top_play = df.sort_values("play", ascending=False).head(10)
    top_play_chart = {
        "titles": [t[:20] for t in top_play["title"].tolist()],
        "plays": [int(x) for x in top_play["play"].tolist()],
        "bvids": top_play["bvid"].tolist(),
    }

    # 图3：播放量区间分布（饼图）
    bins = [0, 10000, 100000, 500000, 1000000, np.inf]
    labels = ["<1万", "1万-10万", "10万-50万", "50万-100万", ">100万"]
    dist = pd.cut(df["play"], bins=bins, labels=labels, right=False).value_counts()
    play_dist_chart = [
        {"name": str(k), "value": int(v)} for k, v in dist.items()
    ]

    # 图4：各互动指标总量（雷达/柱状）
    interaction_totals = {m: int(df[m].sum()) for m in _METRICS if m in df.columns}

    return {
        "empty": False,
        "summary": {
            "video_count": int(len(df)),
            "author_count": int(df["author"].nunique()),
            "total_play": int(df["play"].sum()),
            "avg_play": int(df["play"].mean()),
        },
        "top_authors": top_authors_chart,
        "top_play_videos": top_play_chart,
        "play_distribution": play_dist_chart,
        "interaction_totals": interaction_totals,
    }


# ---------------- 2. KMeans 聚类 ----------------

def clustering(crawl_date: str = None, k: int = 3) -> dict:
    """对视频按互动指标做 KMeans 聚类，返回散点图数据（播放量 vs 点赞）。"""
    df = _load(crawl_date)
    if len(df) < k:
        return {"empty": True, "message": "数据量不足，无法聚类"}

    feats = ["play", "like", "coin", "favorite", "share"]
    X = df[feats].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    df = df.copy()
    df["cluster"] = labels

    # 每个簇的散点（log 便于展示）+ 簇特征均值
    series = []
    for c in range(k):
        sub = df[df["cluster"] == c]
        series.append({
            "name": f"簇{c}（{len(sub)}个）",
            "points": [[int(p), int(l)] for p, l in zip(sub["play"], sub["like"])],
        })
    centers = []
    for c in range(k):
        sub = df[df["cluster"] == c]
        centers.append({
            "cluster": c,
            "count": int(len(sub)),
            "avg_play": int(sub["play"].mean()) if len(sub) else 0,
            "avg_like": int(sub["like"].mean()) if len(sub) else 0,
            "avg_coin": int(sub["coin"].mean()) if len(sub) else 0,
        })
    return {"empty": False, "series": series, "centers": centers}


# ---------------- 3. 关联规则挖掘（自实现 Apriori）----------------

def _apriori(transactions, min_support):
    """返回频繁项集 {frozenset: support}。transactions 为 list[set]。"""
    n = len(transactions)
    # 1-项集
    item_counts = {}
    for t in transactions:
        for item in t:
            item_counts[frozenset([item])] = item_counts.get(frozenset([item]), 0) + 1
    freq = {k: v / n for k, v in item_counts.items() if v / n >= min_support}
    all_freq = dict(freq)

    current = list(freq.keys())
    size = 2
    while current:
        # 生成候选
        items = sorted(set().union(*current)) if current else []
        candidates = [frozenset(c) for c in combinations(items, size)]
        # 计数
        counts = {}
        for cand in candidates:
            cnt = sum(1 for t in transactions if cand.issubset(t))
            if cnt / n >= min_support:
                counts[cand] = cnt / n
        all_freq.update(counts)
        current = list(counts.keys())
        size += 1
        if size > 4:
            break
    return all_freq


def association_rules(crawl_date: str = None, min_support: float = 0.2,
                      min_confidence: float = 0.6) -> dict:
    """挖掘高互动行为之间的关联规则。

    构造事务：对每条视频，若某指标值高于该指标中位数，则认为该视频在此维度"高"，
    对应 item 出现。例如规则「投币→点赞」表示投币高的视频通常点赞也高。
    """
    df = _load(crawl_date)
    if len(df) < 5:
        return {"empty": True, "message": "数据量不足，无法挖掘关联规则"}

    dims = {"播放": "play", "点赞": "like", "投币": "coin", "收藏": "favorite", "转发": "share"}
    medians = {name: df[col].median() for name, col in dims.items()}

    transactions = []
    for _, row in df.iterrows():
        t = {name for name, col in dims.items() if row[col] > medians[name]}
        transactions.append(t)

    freq = _apriori(transactions, min_support)

    rules = []
    for itemset, support in freq.items():
        if len(itemset) < 2:
            continue
        items = list(itemset)
        # 枚举非空真子集作为前件
        for r in range(1, len(items)):
            for ante in combinations(items, r):
                ante = frozenset(ante)
                cons = itemset - ante
                ante_sup = freq.get(ante)
                if not ante_sup:
                    continue
                confidence = support / ante_sup
                if confidence >= min_confidence:
                    rules.append({
                        "rule": f"{' & '.join(sorted(ante))} → {' & '.join(sorted(cons))}",
                        "support": round(support, 3),
                        "confidence": round(confidence, 3),
                    })
    rules.sort(key=lambda x: (x["confidence"], x["support"]), reverse=True)
    return {"empty": False, "rules": rules[:20], "transaction_count": len(transactions)}


# ---------------- 4. 爆款预测 ----------------

def hot_prediction(crawl_date: str = None) -> dict:
    """用互动特征预测视频是否"爆款"（播放量进入前 25%）。

    特征不含 play 本身，避免标签泄漏；输出准确率与特征重要度。
    """
    df = _load(crawl_date)
    if len(df) < 20:
        return {"empty": True, "message": "数据量不足，无法训练预测模型"}

    threshold = df["play"].quantile(0.75)
    y = (df["play"] >= threshold).astype(int)
    feat_names = ["like", "coin", "favorite", "share", "danmaku", "reply", "duration"]
    X = df[feat_names].fillna(0).values

    if y.nunique() < 2:
        return {"empty": True, "message": "样本类别单一，无法训练"}

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    clf = DecisionTreeClassifier(max_depth=4, random_state=42)
    clf.fit(X_train, y_train)
    acc = accuracy_score(y_test, clf.predict(X_test))

    importance = sorted(
        [{"feature": f, "importance": round(float(imp), 3)}
         for f, imp in zip(feat_names, clf.feature_importances_)],
        key=lambda x: x["importance"], reverse=True,
    )
    return {
        "empty": False,
        "play_threshold": int(threshold),
        "hot_count": int(y.sum()),
        "accuracy": round(float(acc), 3),
        "feature_importance": importance,
    }
