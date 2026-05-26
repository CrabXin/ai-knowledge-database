# B站数据分析与 AI 知识库系统

> 系统开发综合实训项目 —— 基于多技术栈的数据分析与 AI 知识库构建（可落地版）

一个完整可运行的全栈系统：从 B 站真实采集视频数据 → 清洗 → 多存储入库（CSV + MongoDB + Redis）→
数据挖掘 + Spark 分布式分析 + ECharts 可视化 → 基于本地离线大模型（Ollama）的知识库问答。
前端为「左侧菜单 + 右侧内容」布局，后端区分超级用户/管理员/普通用户三级权限。

---

## 一、功能总览

| 实训模块 | 本系统实现 |
| --- | --- |
| 模块一 数据采集 | B站搜索接口（WBI 签名）+ 视频详情接口，采集标题/URL/播放/UP主/点赞/投币/收藏/转发等 |
| 模块二 数据清洗 | `cleaner.py`：万/亿换算、标题去标签 |
| 模块三 数据存储 | CSV 主存储（`backend/data/videos.csv`）+ 同步入库 **MongoDB + Redis** 两个存储系统，按 `crawl_date` 区分日期 |
| 模块四 数据挖掘 | KMeans 聚类、Apriori 关联规则、决策树爆款预测 |
| 模块五 分布式分析 | **Spark（PySpark）真实分布式分析** 5 种（UP主排行/播放统计/区间分布/互动均值/时长分桶），不可用时 pandas 兜底 |
| 模块六 数据可视化 | ECharts 4 个图：UP主Top10、播放Top10、播放区间饼图、聚类散点 |
| 模块七 AI 知识库 | CSV 检索 + Ollama 本地大模型生成，无模型时规则统计兜底 |
| 其他 1 角色权限 | 登录区分 admin/user，仅管理员可采集 |
| 其他 2 自动采集 | APScheduler 每日 02:00 自动采集前一天数据 |
| 其他 3/4 按日期查看 | 分析与问答均支持选择采集日期 |

### 角色与默认账号

| 账号 | 密码 | 角色 | 权限 |
| --- | --- | --- | --- |
| `superadmin` | `super123` | 超级用户 | 新增管理员/普通用户 + 采集 + 查看分析 + AI问答 |
| `admin` | `admin123` | 管理员 | 新增普通用户 + 采集数据 + 查看分析 + AI问答 |
| `user` | `user123` | 普通用户 | 查看分析 + AI问答（不能采集、不能管理用户） |

> 角色层级：**超级用户 > 管理员 > 普通用户**。超级用户可在「用户管理」页新增管理员或普通用户；
> 管理员只能新增普通用户；新建的账号可立即用于登录。

---

## 二、技术栈

- **后端**：Python 3.8+ / FastAPI / Pandas / scikit-learn / APScheduler / PyJWT / Requests
- **前端**：React 18 + Vite + ECharts + Axios
- **AI**：Ollama 本地离线大模型（`qwen2.5:3b` / `llama3:8b`），LangChain 生态
- **存储**：CSV 文件 + **MongoDB**（文档存储，按 bvid+日期 upsert）+ **Redis**（Hash 存视频、ZSet 维护播放量排行榜）
- **分布式计算**：**Apache Spark 3.5 / PySpark**（本地 SparkSession，Spark SQL + DataFrame）

> 模块三按“任选 2 个以上存储系统”的要求选用 **MongoDB + Redis**；Spark 运行依赖 JDK（已在 `E:\JDK17`）。

---

## 三、目录结构

```
ai_knowldge_database/
├── backend/
│   ├── main.py          # FastAPI 入口与路由
│   ├── config.py        # 全局配置（路径/字段/默认参数）
│   ├── auth.py          # 登录、JWT、角色权限
│   ├── crawler.py       # B站真实爬虫（WBI 签名）
│   ├── cleaner.py       # 数据清洗（万→数字）
│   ├── analysis.py      # 聚类/关联规则/预测/统计（单机）
│   ├── spark_analysis.py# 模块五：Spark 分布式分析（5 种，pandas 兜底）
│   ├── db_store.py      # 模块三：写入 MongoDB + Redis + 状态读取
│   ├── ai_qa.py         # Ollama + 规则兜底问答
│   ├── scheduler.py     # 定时采集 + 后台手动采集
│   ├── storage.py       # CSV 读写、去重、状态
│   ├── requirements.txt
│   └── data/            # 运行时生成：videos.csv / users.csv / crawl_status.json
├── frontend/            # React + Vite
│   └── src/
│       ├── App.jsx               # 左菜单右内容布局
│       ├── components/           # Login / EChart
│       └── pages/                # CrawlerSettings / Analysis / AiQa / UserManagement
├── tools/
│   └── redis/           # 自带便携版 Redis（redis-server.exe）
├── docs/
│   ├── 数据字段解析文档.md
│   └── architecture.png          # 系统架构图
└── README.md
```

---

## 四、运行步骤

> 国内安装依赖建议用镜像（避免代理问题）：
> `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 0. 启动存储系统（模块三：MongoDB + Redis）

```powershell
# MongoDB：作为系统服务运行即可（默认端口 27017），无需手动启动
# Redis：使用项目自带便携版（保持该窗口不关）
cd tools\redis
.\redis-server.exe --port 6379 --save "" --appendonly no
```

> 存储系统未启动时后端仍可运行，采集时会跳过入库，数据始终写入 CSV，不会丢失。

### 1. 启动后端

```powershell
cd backend
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

后端启动后会自动创建默认用户（含超级用户）并开启每日定时采集任务。

### 2. （可选）启动本地大模型

```powershell
ollama serve            # 若未作为服务自启
ollama pull qwen2.5:3b  # 若本地无模型
```

未启动 Ollama 时，AI 问答自动回退为基于 CSV 的规则统计回答，系统仍可用。

### 3. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 **http://localhost:5173** ，用上表账号登录。

### 4. 生产部署（可选）

```powershell
cd frontend && npm run build      # 生成 frontend/dist
cd ../backend && python -m uvicorn main:app --port 8000
```

后端检测到 `frontend/dist` 后会直接托管前端，访问 http://127.0.0.1:8000 即可。

---

## 五、使用流程

1. 用 `admin`（或 `superadmin`）登录 → 进入「爬虫基本设置」→ 设置关键词（默认"大数据技术"）和页数 → 点击"开始采集"，进度实时刷新；页面下方的「存储系统状态」卡片显示 MongoDB / Redis 的连接状态与数据量；
2. 进入「分析结果」→ 查看指标卡、4 个可视化图、关联规则与爆款预测；点击底部「运行 Spark 分布式分析」可查看 Spark 的 5 种分布式分析结果（首次启动约十几秒），可切换采集日期；
3. 进入「AI回答」→ 提问（如"播放量最高的视频是哪个？"），查看本地大模型回答与数据证据；
4. 超级用户/管理员可进入「用户管理」新增账号（超级用户可建管理员，管理员可建普通用户）。

> 数据字段含义与采集/清洗规则详见 [`docs/数据字段解析文档.md`](docs/数据字段解析文档.md)。

---

## 六、注意事项

- B 站有反爬风控，单次采集页数不宜过大、请求间隔不宜过小；触发风控时状态栏会提示，稍后重试即可。
- 勾选"补全互动数据"会逐条调用详情接口补全点赞/投币/转发，更完整但更慢。
- **存储**：采集后数据同步写入 MongoDB（库 `bili_kb`）与 Redis；任一不可用会自动跳过，不影响 CSV 主流程。
- **Spark**：首次运行需启动本地 SparkSession（约十几秒）；Windows 下已自动绑定 `127.0.0.1` 并指定 `PYSPARK_PYTHON` 以规避 worker 回连问题，Spark 不可用时回退 pandas。
- 本项目仅用于学习与教学，请遵守目标网站的 robots 协议与使用条款，合理控制采集频率。
