# -*- coding: utf-8 -*-
"""绘制系统总体架构图（分层架构），输出 docs/architecture.png。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(10, 7.2), dpi=200)
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

C_BAND = "#e8f4fb"; C_EDGE = "#2b7bb9"
C_BOX = "#ffffff"; C_BOX_EDGE = "#4a90c2"
C_EXT = "#fff4e6"; C_EXT_EDGE = "#e08e2b"
C_STORE = "#eafaf1"; C_STORE_EDGE = "#27ae60"


def band(x, y, w, h, color, edge, title="", title_color="#1a5276"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=2",
                                fc=color, ec=edge, lw=1.6))
    if title:
        ax.text(x + 1.5, y + h - 2.4, title, fontsize=11, fontweight="bold",
                color=title_color, ha="left", va="top")


def box(x, y, w, h, text, fc=C_BOX, ec=C_BOX_EDGE, fs=9.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.5",
                                fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, fontsize=fs, ha="center", va="center", color="#222")


def varrow(x, y1, y2, label="", lx=1.2):
    a = FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>", mutation_scale=16,
                        lw=1.6, color="#555", shrinkA=0, shrinkB=0)
    ax.add_patch(a)
    if label:
        ax.text(x + lx, (y1 + y2) / 2, label, fontsize=8.5, ha="left", va="center",
                color="#444", style="italic")


# ---- 用户层 ----
band(5, 90, 90, 8, "#f3e9f7", "#8e44ad", "用户层", "#6c3483")
box(30, 91, 28, 5.5, "管理员 admin（可采集）", fc="#fbeef7", ec="#8e44ad")
box(60, 91, 28, 5.5, "普通用户 user（只读）", fc="#fbeef7", ec="#8e44ad")

# ---- 前端展示层 ----
band(5, 73, 90, 13, C_BAND, C_EDGE, "前端展示层（React 18 + Vite，左菜单 + 右内容）")
for i, t in enumerate(["登录页", "爬虫基本设置", "分析结果", "AI回答"]):
    box(8 + i * 22, 74, 19, 5.5, t)

# ---- 应用服务层 ----
band(5, 54, 90, 14, C_BAND, C_EDGE, "应用服务层（FastAPI + Uvicorn，main.py / auth.py）")
box(9, 55, 24, 5.5, "RESTful 路由分发")
box(38, 55, 24, 5.5, "JWT 登录鉴权")
box(67, 55, 24, 5.5, "角色权限校验\n(require_admin)", fs=8.5)

# ---- 业务逻辑层 ----
band(5, 30, 90, 19, C_BAND, C_EDGE, "业务逻辑层（核心处理模块）")
box(7, 38, 20, 8, "数据采集\ncrawler.py\n(WBI签名)", fs=8.5)
box(29, 38, 20, 8, "数据清洗\ncleaner.py\n(万→数字)", fs=8.5)
box(51, 38, 20, 8, "分析挖掘\nanalysis.py\nKMeans/Apriori\n/决策树", fs=8)
box(73, 38, 20, 8, "AI问答\nai_qa.py\n(检索+生成)", fs=8.5)
box(29, 31, 42, 5.5, "定时调度 scheduler.py（APScheduler 每日凌晨自动采集）", fs=8.5)

# ---- 数据存储层 ----
band(5, 17, 90, 10, C_STORE, C_STORE_EDGE, "数据存储层")
box(20, 18, 26, 5.5, "videos.csv（采集数据）", fc="#f0fbf5", ec=C_STORE_EDGE)
box(54, 18, 26, 5.5, "users.csv（用户/角色）", fc="#f0fbf5", ec=C_STORE_EDGE)

# ---- 外部服务 ----
band(5, 2, 90, 11, C_EXT, C_EXT_EDGE, "外部服务")
box(12, 3.2, 34, 6, "B站开放接口\n搜索 / 视频详情接口", fc="#fff8ef", ec=C_EXT_EDGE, fs=8.5)
box(54, 3.2, 34, 6, "Ollama 本地离线大模型\nqwen2.5:3b / llama3:8b", fc="#fff8ef", ec=C_EXT_EDGE, fs=8.5)

# ---- 连接箭头 ----
varrow(50, 90, 86.3, "")
varrow(50, 73, 68.3, "RESTful API（携带JWT令牌）")
varrow(50, 54, 49.3, "")
varrow(50, 30, 27.3, "读/写 CSV")
# 采集 -> B站接口（双向）
ax.add_patch(FancyArrowPatch((17, 38), (24, 9.2), arrowstyle="<|-|>", mutation_scale=14,
                             lw=1.5, color="#e08e2b", shrinkA=2, shrinkB=2,
                             connectionstyle="arc3,rad=-0.15"))
# AI问答 -> Ollama（双向）
ax.add_patch(FancyArrowPatch((83, 38), (71, 9.2), arrowstyle="<|-|>", mutation_scale=14,
                             lw=1.5, color="#e08e2b", shrinkA=2, shrinkB=2,
                             connectionstyle="arc3,rad=0.15"))

ax.text(50, 99.2, "图  系统总体架构", fontsize=13, fontweight="bold",
        ha="center", va="center", color="#154360")

plt.tight_layout()
plt.savefig("E:/aiOperation/ai_knowldge_database/docs/architecture.png",
            bbox_inches="tight", facecolor="white")
print("architecture.png saved")
