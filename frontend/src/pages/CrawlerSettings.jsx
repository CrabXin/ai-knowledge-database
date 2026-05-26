// 爬虫基本设置页：配置采集参数、启动采集（仅管理员）、轮询进度、预览最新数据。
import { useEffect, useRef, useState } from 'react'
import api from '../api'

export default function CrawlerSettings({ user }) {
  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  const [form, setForm] = useState({ keyword: '大数据技术', pages: 3, delay: 1.0, enrich: true })
  const [status, setStatus] = useState({ running: false, message: '加载中...' })
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [store, setStore] = useState(null)
  const timerRef = useRef(null)

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const loadStatus = async () => {
    try {
      const { data } = await api.get('/crawl/status')
      setStatus(data)
      // 采集进行中时持续刷新数据预览，体现"持续更新数据"
      if (!data.running && timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
        loadData()
      }
    } catch (e) { /* ignore */ }
  }

  const loadData = async () => {
    const { data } = await api.get('/data', { params: { limit: 20 } })
    setRows(data.rows)
    setTotal(data.total)
  }

  const loadStore = async () => {
    try {
      const { data } = await api.get('/storage/status')
      setStore(data)
    } catch (e) { /* ignore */ }
  }

  useEffect(() => {
    loadStatus()
    loadData()
    loadStore()
    return () => timerRef.current && clearInterval(timerRef.current)
  }, [])

  const startCrawl = async () => {
    try {
      await api.post('/crawl/start', form)
      // 启动后开始轮询进度，每 2 秒刷新一次状态与数据
      if (!timerRef.current) {
        timerRef.current = setInterval(() => { loadStatus(); loadData(); loadStore() }, 2000)
      }
      loadStatus()
    } catch (e) {
      alert(e.response?.data?.detail || '启动失败')
    }
  }

  return (
    <div>
      <h2 className="page-title">爬虫基本设置</h2>

      <div className="card">
        <h3>采集参数</h3>
        <div className="form-row">
          <label>搜索关键词</label>
          <input type="text" value={form.keyword} onChange={(e) => setField('keyword', e.target.value)} />
        </div>
        <div className="form-row">
          <label>采集页数</label>
          <input type="number" min="1" max="50" value={form.pages}
                 onChange={(e) => setField('pages', Number(e.target.value))} />
          <span className="muted">每页约 20-42 条视频</span>
        </div>
        <div className="form-row">
          <label>请求间隔(秒)</label>
          <input type="number" min="0.2" step="0.1" value={form.delay}
                 onChange={(e) => setField('delay', Number(e.target.value))} />
          <span className="muted">间隔越大越不易触发反爬</span>
        </div>
        <div className="form-row">
          <label>补全互动数据</label>
          <input type="checkbox" checked={form.enrich}
                 onChange={(e) => setField('enrich', e.target.checked)} />
          <span className="muted">勾选后逐条调用视频详情接口补全 点赞/投币/转发</span>
        </div>
        <div className="form-row">
          <label></label>
          <button className="btn" onClick={startCrawl} disabled={!isAdmin || status.running}>
            {status.running ? '采集进行中...' : '开始采集'}
          </button>
          {!isAdmin && <span className="muted">仅管理员可执行采集</span>}
        </div>
      </div>

      <div className="card">
        <h3>采集状态</h3>
        <div className={`status-box ${status.running ? 'status-running' : 'status-idle'}`}>
          {status.running ? '⏳ ' : '✅ '}{status.message}
          {status.fetched ? `（本次 ${status.fetched} 条）` : ''}
        </div>
        <p className="muted" style={{ marginTop: 10 }}>
          系统每日凌晨 02:00 自动采集前一天数据；手动采集会增量更新到同一 CSV，重复视频按最新数据覆盖。
        </p>
      </div>

      <div className="card">
        <h3>存储系统状态（模块三：清洗后数据同步入库）</h3>
        <p className="muted" style={{ marginBottom: 10 }}>
          清洗后的数据除存为 CSV 外，同步写入以下存储系统：
        </p>
        <div className="metric-grid">
          {store && Object.entries(store).map(([name, s]) => (
            <div key={name} className="metric"
                 style={{ background: s.connected ? 'linear-gradient(135deg,#27ae60,#1e8449)' : 'linear-gradient(135deg,#c0392b,#922b21)' }}>
              <div className="num">{name === 'mongodb' ? 'MongoDB' : 'Redis'}</div>
              <div className="label">
                {s.connected
                  ? `已连接 v${s.version}　数据量：${s.total_docs ?? s.total_videos}`
                  : `未连接：${s.error || '不可用'}`}
              </div>
            </div>
          ))}
          {!store && <span className="muted">加载中...</span>}
        </div>
      </div>

      <div className="card">
        <h3>最新数据预览（库内共 {total} 条，按播放量降序取前 20）</h3>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>标题</th><th>UP主</th><th>播放</th><th>点赞</th>
                <th>投币</th><th>收藏</th><th>转发</th><th>采集日期</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.bvid}>
                  <td><a href={r.url} target="_blank" rel="noreferrer">{r.title?.slice(0, 28)}</a></td>
                  <td>{r.author}</td><td>{r.play}</td><td>{r.like}</td>
                  <td>{r.coin}</td><td>{r.favorite}</td><td>{r.share}</td><td>{r.crawl_date}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan="8" className="muted">暂无数据，请先采集</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
