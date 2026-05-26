// AI回答页：基于 CSV 知识库提问，展示本地大模型(Ollama)或规则兜底的回答与数据证据。
import { useEffect, useState } from 'react'
import api from '../api'

const PRESETS = ['哪个UP主视频最多？', '播放量最高的视频是哪个？', '哪些视频点赞投币最高？', '数据集一共有多少条数据？']

export default function AiQa() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [engine, setEngine] = useState('')

  useEffect(() => {
    api.get('/ai/status').then(({ data }) => setEngine(data.engine))
  }, [])

  const ask = async (q) => {
    const query = q || question
    if (!query.trim()) return
    setQuestion(query)
    setLoading(true)
    setResult(null)
    try {
      const { data } = await api.post('/ai/ask', { question: query })
      setResult(data)
    } catch (e) {
      setResult({ answer: e.response?.data?.detail || '请求失败', engine: 'error', evidence: {} })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="page-title">AI 知识库问答</h2>

      <div className="card">
        <h3>
          基于采集的 CSV 内容构建本地知识库
          <span className="engine-badge" style={{ marginLeft: 10 }}>
            当前引擎：{engine.startsWith('ollama') ? `本地大模型 ${engine.replace('ollama:', '')}` : '规则统计(兜底)'}
          </span>
        </h3>
        <div className="form-row">
          <input type="text" style={{ flex: 1, minWidth: 0 }} placeholder="请输入问题，例如：播放量最高的视频是哪个？"
                 value={question} onChange={(e) => setQuestion(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && ask()} />
          <button className="btn btn-green" onClick={() => ask()} disabled={loading}>
            {loading ? '思考中...' : '问 AI'}
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
          {PRESETS.map((p) => (
            <span key={p} className="engine-badge" style={{ cursor: 'pointer' }} onClick={() => ask(p)}>{p}</span>
          ))}
        </div>
      </div>

      {loading && <div className="card"><p className="muted">🤖 AI 思考中，请稍候...</p></div>}

      {result && !loading && (
        <div className="card">
          <h3>回答 <span className="engine-badge">{result.engine}</span></h3>
          <div className="answer-box">{result.answer}</div>
          {result.evidence && Object.keys(result.evidence).length > 0 && (
            <div className="evidence">
              <b>数据证据（来自知识库）：</b>
              <ul>
                {Object.entries(result.evidence).map(([k, v]) => <li key={k}>{k}：{v}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
