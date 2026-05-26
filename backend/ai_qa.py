"""AI 知识库问答模块（实训模块七）。

基于采集的 CSV 内容构建本地知识库问答：
1. 检索层（规则）：从 CSV 计算与问题相关的精确事实（如播放最高视频、视频最多的UP主等），
   既作为给大模型的"上下文证据"，也作为无模型时的兜底答案；
2. 生成层（Ollama 本地离线大模型）：把事实证据 + 用户问题交给本地模型，生成自然语言回答；
3. 当本地没有可用模型 / 服务不可达时，自动回退为规则统计答案，保证功能始终可用。
"""
import requests

import config
import storage

# 访问本地 Ollama 时绕过系统代理（localhost 不应走代理，否则会 502）
_ollama_session = requests.Session()
_ollama_session.trust_env = False


# ---------------- 检索层：从 CSV 抽取事实 ----------------

def _build_facts(df) -> dict:
    """从数据集中抽取常用统计事实，作为知识库证据。"""
    facts = {}
    if df.empty:
        return facts
    top_play = df.loc[df["play"].idxmax()]
    facts["播放量最高的视频"] = f"《{top_play['title']}》（UP主：{top_play['author']}），播放量 {int(top_play['play'])}"
    top_like = df.loc[df["like"].idxmax()]
    facts["点赞数最高的视频"] = f"《{top_like['title']}》（UP主：{top_like['author']}），点赞数 {int(top_like['like'])}"
    top_coin = df.loc[df["coin"].idxmax()]
    facts["投币数最高的视频"] = f"《{top_coin['title']}》（UP主：{top_coin['author']}），投币数 {int(top_coin['coin'])}"
    df_lc = df.assign(lc=df["like"] + df["coin"])
    top_lc = df_lc.loc[df_lc["lc"].idxmax()]
    facts["点赞投币合计最高的视频"] = f"《{top_lc['title']}》（UP主：{top_lc['author']}），点赞{int(top_lc['like'])}+投币{int(top_lc['coin'])}"
    author_counts = df.groupby("author").size().sort_values(ascending=False)
    facts["视频数最多的UP主"] = f"{author_counts.index[0]}，共 {int(author_counts.iloc[0])} 个视频"
    facts["数据集规模"] = f"共 {len(df)} 条视频，{df['author'].nunique()} 位UP主，总播放量 {int(df['play'].sum())}"
    return facts


def _retrieve_answer(question: str, facts: dict, df) -> str:
    """规则匹配：根据问题关键词返回最相关的事实答案。"""
    q = question
    # 关键词到事实的映射（按优先级）
    if "最多" in q and ("up" in q.lower() or "博主" in q or "主" in q):
        return facts.get("视频数最多的UP主", "")
    if "播放" in q and ("最高" in q or "最多" in q or "最大" in q):
        return facts.get("播放量最高的视频", "")
    if "点赞" in q and "投币" in q:
        return facts.get("点赞投币合计最高的视频", "")
    if "点赞" in q and ("最高" in q or "最多" in q):
        return facts.get("点赞数最高的视频", "")
    if "投币" in q and ("最高" in q or "最多" in q):
        return facts.get("投币数最高的视频", "")
    if "多少" in q or "规模" in q or "几条" in q or "总" in q:
        return facts.get("数据集规模", "")
    # 默认：返回所有事实拼接
    return "；".join(f"{k}：{v}" for k, v in facts.items())


# ---------------- 生成层：Ollama 本地大模型 ----------------

def _pick_ollama_model() -> str:
    """探测本地 Ollama 可用模型，返回首选模型名；不可用返回 None。"""
    try:
        resp = _ollama_session.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=3)
        if resp.status_code != 200:
            return None
        available = {m["name"] for m in resp.json().get("models", [])}
        for preferred in config.OLLAMA_MODELS:
            if preferred in available:
                return preferred
        # 没有匹配到首选，则用任意一个可用模型
        return next(iter(available)) if available else None
    except requests.RequestException:
        return None


def _ask_ollama(model: str, question: str, facts: dict) -> str:
    """调用 Ollama 生成回答，失败返回 None。"""
    evidence = "\n".join(f"- {k}：{v}" for k, v in facts.items())
    prompt = (
        "你是B站视频数据分析知识库助手。请仅依据下面提供的【数据事实】回答用户问题，"
        "用简洁的中文回答，不要编造数据。\n\n"
        f"【数据事实】\n{evidence}\n\n"
        f"【用户问题】{question}\n\n【回答】"
    )
    try:
        resp = _ollama_session.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("response", "").strip()
    except requests.RequestException:
        return None


# ---------------- 对外入口 ----------------

def answer(question: str, crawl_date: str = None) -> dict:
    """回答用户问题。

    Returns:
        {"answer": str, "engine": "ollama:<model>"|"rule", "evidence": dict}
    """
    df = storage.load_videos(crawl_date)
    if df.empty:
        return {"answer": "知识库暂无数据，请先采集数据后再提问。", "engine": "rule", "evidence": {}}

    facts = _build_facts(df)
    rule_answer = _retrieve_answer(question, facts, df)

    model = _pick_ollama_model()
    if model:
        llm_answer = _ask_ollama(model, question, facts)
        if llm_answer:
            return {"answer": llm_answer, "engine": f"ollama:{model}", "evidence": facts}

    # 兜底：规则统计答案
    return {"answer": rule_answer, "engine": "rule", "evidence": facts}
