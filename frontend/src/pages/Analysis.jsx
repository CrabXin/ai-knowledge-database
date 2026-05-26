// 分析结果页：统计指标卡 + 4个 ECharts 可视化图 + 关联规则/爆款预测表，支持按日期查看。
import { useEffect, useState } from 'react'
import api from '../api'
import EChart from '../components/EChart'

export default function Analysis() {
  const [dates, setDates] = useState([])
  const [date, setDate] = useState('')
  const [stats, setStats] = useState(null)
  const [cluster, setCluster] = useState(null)
  const [assoc, setAssoc] = useState(null)
  const [pred, setPred] = useState(null)
  const [loading, setLoading] = useState(false)
  const [spark, setSpark] = useState(null)
  const [sparkLoading, setSparkLoading] = useState(false)

  const loadDates = async () => {
    const { data } = await api.get('/dates')
    setDates(data.dates)
  }

  const loadAll = async (d) => {
    setLoading(true)
    const params = d ? { crawl_date: d } : {}
    try {
      const [s, c, a, p] = await Promise.all([
        api.get('/analysis/statistics', { params }),
        api.get('/analysis/clustering', { params }),
        api.get('/analysis/association', { params }),
        api.get('/analysis/prediction', { params }),
      ])
      setStats(s.data); setCluster(c.data); setAssoc(a.data); setPred(p.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadDates(); loadAll('') }, [])

  const onDateChange = (e) => { setDate(e.target.value); setSpark(null); loadAll(e.target.value) }

  const runSpark = async () => {
    setSparkLoading(true)
    try {
      const params = date ? { crawl_date: date } : {}
      const { data } = await api.get('/analysis/spark', { params })
      setSpark(data)
    } catch (e) {
      setSpark({ empty: true, message: 'Spark 分析请求失败' })
    } finally {
      setSparkLoading(false)
    }
  }

  if (loading || !stats) return <div><h2 className="page-title">分析结果</h2><p className="muted">加载中...</p></div>
  if (stats.empty) return <div><h2 className="page-title">分析结果</h2><div className="card">暂无数据，请先在「爬虫基本设置」采集。</div></div>

  // 图1：UP主视频数 Top10
  const optAuthors = {
    title: { text: '视频数最多的 UP主 Top10', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {}, grid: { left: 100, right: 20, top: 40, bottom: 20 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: stats.top_authors.names.slice().reverse() },
    series: [{ type: 'bar', data: stats.top_authors.counts.slice().reverse(), itemStyle: { color: '#00a1d6' } }],
  }
  // 图2：播放量 Top10 视频
  const optPlay = {
    title: { text: '播放量最高的视频 Top10', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' }, grid: { left: 60, right: 20, top: 40, bottom: 80 },
    xAxis: { type: 'category', data: stats.top_play_videos.titles, axisLabel: { interval: 0, rotate: 40, fontSize: 10 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: stats.top_play_videos.plays, itemStyle: { color: '#fb7299' } }],
  }
  // 图3：播放量区间分布
  const optDist = {
    title: { text: '播放量区间分布', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item' }, legend: { bottom: 0 },
    series: [{ type: 'pie', radius: ['35%', '65%'], data: stats.play_distribution, label: { fontSize: 11 } }],
  }
  // 图4：KMeans 聚类散点（播放量 vs 点赞）
  const optCluster = {
    title: { text: 'KMeans 聚类：播放量 vs 点赞', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {}, legend: { bottom: 0 },
    xAxis: { name: '播放量', type: 'value' }, yAxis: { name: '点赞', type: 'value' },
    series: (cluster?.series || []).map((s) => ({ name: s.name, type: 'scatter', data: s.points, symbolSize: 8 })),
  }

  return (
    <div>
      <h2 className="page-title">分析结果</h2>

      <div className="toolbar">
        <label>查看日期：</label>
        <select value={date} onChange={onDateChange}>
          <option value="">全部日期</option>
          {dates.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {/* 指标卡 */}
      <div className="metric-grid" style={{ marginBottom: 20 }}>
        <div className="metric"><div className="num">{stats.summary.video_count}</div><div className="label">视频总数</div></div>
        <div className="metric"><div className="num">{stats.summary.author_count}</div><div className="label">UP主数量</div></div>
        <div className="metric"><div className="num">{stats.summary.total_play.toLocaleString()}</div><div className="label">总播放量</div></div>
        <div className="metric"><div className="num">{stats.summary.avg_play.toLocaleString()}</div><div className="label">平均播放量</div></div>
      </div>

      {/* 4 个可视化图 */}
      <div className="charts-grid">
        <div className="card"><EChart option={optAuthors} /></div>
        <div className="card"><EChart option={optPlay} /></div>
        <div className="card"><EChart option={optDist} /></div>
        <div className="card"><EChart option={optCluster} /></div>
      </div>

      {/* 关联规则 */}
      <div className="card">
        <h3>关联规则挖掘（高互动行为之间的关联，Apriori）</h3>
        {assoc?.empty ? <p className="muted">{assoc.message}</p> : (
          <table>
            <thead><tr><th>关联规则</th><th>支持度</th><th>置信度</th></tr></thead>
            <tbody>
              {assoc.rules.map((r, i) => (
                <tr key={i}><td>{r.rule}</td><td>{r.support}</td><td>{r.confidence}</td></tr>
              ))}
              {assoc.rules.length === 0 && <tr><td colSpan="3" className="muted">未挖掘到满足阈值的规则</td></tr>}
            </tbody>
          </table>
        )}
      </div>

      {/* 爆款预测 */}
      <div className="card">
        <h3>爆款预测（决策树：用互动特征预测是否高播放）</h3>
        {pred?.empty ? <p className="muted">{pred.message}</p> : (
          <div>
            <p style={{ marginBottom: 10 }}>
              爆款判定阈值（播放量前25%）：<b>{pred.play_threshold?.toLocaleString()}</b>；
              爆款视频数：<b>{pred.hot_count}</b>；
              模型准确率：<b>{(pred.accuracy * 100).toFixed(1)}%</b>
            </p>
            <table>
              <thead><tr><th>特征</th><th>重要度</th></tr></thead>
              <tbody>
                {pred.feature_importance.map((f) => (
                  <tr key={f.feature}><td>{f.feature}</td><td>{f.importance}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 模块五：Spark 分布式分析 */}
      <div className="card">
        <h3>
          Spark 分布式分析（模块五）
          {spark && !spark.empty && <span className="engine-badge" style={{ marginLeft: 10 }}>{spark.engine}</span>}
        </h3>
        {!spark && (
          <div className="form-row">
            <button className="btn" onClick={runSpark} disabled={sparkLoading}>
              {sparkLoading ? 'Spark 启动并计算中（约十几秒）...' : '运行 Spark 分布式分析'}
            </button>
            <span className="muted">使用 SparkSQL/DataFrame 对当前数据做 5 种分布式分析</span>
          </div>
        )}
        {spark && spark.empty && <p className="muted">{spark.message}</p>}
        {spark && !spark.empty && (
          <div>
            {spark.fallback_reason && (
              <div className="status-box status-running" style={{ marginBottom: 12 }}>
                ⚠ Spark 未就绪，已用 pandas 等价兜底：{spark.fallback_reason}
              </div>
            )}
            <div className="charts-grid">
              <EChart option={{
                title: { text: 'Spark①UP主视频数Top10', left: 'center', textStyle: { fontSize: 13 } },
                tooltip: {}, grid: { left: 100, right: 20, top: 36, bottom: 20 },
                xAxis: { type: 'value' },
                yAxis: { type: 'category', data: spark.top_authors.map(a => a.author).reverse() },
                series: [{ type: 'bar', data: spark.top_authors.map(a => a.count).reverse(), itemStyle: { color: '#e6a23c' } }],
              }} />
              <EChart option={{
                title: { text: 'Spark③播放量区间分布', left: 'center', textStyle: { fontSize: 13 } },
                tooltip: { trigger: 'item' }, legend: { bottom: 0 },
                series: [{ type: 'pie', radius: ['35%', '65%'], data: spark.play_distribution, label: { fontSize: 11 } }],
              }} />
              <EChart option={{
                title: { text: 'Spark⑤时长分桶 vs 平均播放', left: 'center', textStyle: { fontSize: 13 } },
                tooltip: { trigger: 'axis' }, grid: { left: 60, right: 20, top: 36, bottom: 30 },
                xAxis: { type: 'category', data: spark.duration_vs_play.map(d => d.dur) },
                yAxis: { type: 'value' },
                series: [{ type: 'bar', data: spark.duration_vs_play.map(d => d.avg_play), itemStyle: { color: '#409eff' } }],
              }} />
              <EChart option={{
                title: { text: 'Spark④各互动指标平均值', left: 'center', textStyle: { fontSize: 13 } },
                tooltip: {}, grid: { left: 60, right: 20, top: 36, bottom: 30 },
                xAxis: { type: 'category', data: Object.keys(spark.avg_interactions) },
                yAxis: { type: 'value' },
                series: [{ type: 'bar', data: Object.values(spark.avg_interactions), itemStyle: { color: '#67c23a' } }],
              }} />
            </div>
            <p style={{ marginTop: 12 }}>
              <b>Spark②播放量统计：</b>
              最小 {spark.play_stats.min.toLocaleString()}，最大 {spark.play_stats.max.toLocaleString()}，
              平均 {spark.play_stats.avg.toLocaleString()}，总计 {spark.play_stats.sum.toLocaleString()}，
              标准差 {spark.play_stats.std.toLocaleString()}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
