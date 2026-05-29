// AI回答页：基于 CSV 知识库的多轮对话。每次提问带上前端生成的 session_id，
// 后端按会话在进程内存里维护上下文（服务重启即清空）。
import { useEffect, useRef, useState } from 'react'
import api from '../api'

const PRESETS = ['哪个UP主视频最多？', '播放量最高的视频是哪个？', '哪些视频点赞投币最高？', '数据集一共有多少条数据？']

export default function AiQa() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([]) // [{role:'user'|'assistant', content, engine?, evidence?}]
  const [loading, setLoading] = useState(false)
  const [engine, setEngine] = useState('')
  // 会话标识：组件首次挂载时生成一次，整个会话期间不变（支持多标签页各自独立）
  const sessionId = useRef(crypto.randomUUID())
  const logRef = useRef(null)

  useEffect(() => {
    api.get('/ai/status').then(({ data }) => setEngine(data.engine))
  }, [])

  // 新消息进来时滚到底部
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages, loading])

  const ask = async (q) => {
    const query = (q || question).trim()
    if (!query || loading) return
    setQuestion('')
    setMessages((prev) => [...prev, { role: 'user', content: query }])
    setLoading(true)
    try {
      const { data } = await api.post('/ai/ask', { question: query, session_id: sessionId.current })
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer, engine: data.engine, evidence: data.evidence }])
    } catch (e) {
      const detail = e.response?.data?.detail || '请求失败'
      setMessages((prev) => [...prev, { role: 'assistant', content: detail, engine: 'error', evidence: {} }])
    } finally {
      setLoading(false)
    }
  }

  const clearChat = async () => {
    try {
      await api.post('/ai/reset', { session_id: sessionId.current })
    } catch (e) {
      // 后端清理失败不阻塞前端清屏（最坏情况是历史在内存里多留一会，下次重启清空）
    }
    setMessages([])
  }

  return (
    <div>
      <h2 className="page-title">AI 知识库问答</h2>

      <div className="card">
        <h3>
          基于采集的 CSV 内容构建本地知识库（支持多轮上下文）
          <span className="engine-badge" style={{ marginLeft: 10 }}>
            当前引擎：{engine.startsWith('ollama') ? `本地大模型 ${engine.replace('ollama:', '')}` : '规则统计(兜底)'}
          </span>
        </h3>

        {/* 对话记录 */}
        <div ref={logRef} style={{ maxHeight: 420, overflowY: 'auto', margin: '12px 0', padding: 4 }}>
          {messages.length === 0 && !loading && (
            <p className="muted">输入问题开始对话，AI 会记住本次会话的上下文。</p>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div style={{
                maxWidth: '78%',
                padding: '8px 12px',
                borderRadius: 10,
                background: m.role === 'user' ? '#e8f0fe' : '#f5f5f5',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {m.role === 'assistant' && m.engine && (
                  <span className="engine-badge" style={{ marginBottom: 6, display: 'inline-block' }}>{m.engine}</span>
                )}
                <div>{m.content}</div>
                {m.role === 'assistant' && m.evidence && Object.keys(m.evidence).length > 0 && (
                  <details style={{ marginTop: 6 }}>
                    <summary className="muted" style={{ cursor: 'pointer' }}>数据证据（来自知识库）</summary>
                    <ul style={{ margin: '6px 0 0' }}>
                      {Object.entries(m.evidence).map(([k, v]) => <li key={k}>{k}：{v}</li>)}
                    </ul>
                  </details>
                )}
              </div>
            </div>
          ))}
          {loading && <p className="muted">🤖 AI 思考中，请稍候...</p>}
        </div>

        <div className="form-row">
          <input type="text" style={{ flex: 1, minWidth: 0 }} placeholder="请输入问题，例如：播放量最高的视频是哪个？"
                 value={question} onChange={(e) => setQuestion(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && ask()} />
          <button className="btn btn-green" onClick={() => ask()} disabled={loading}>
            {loading ? '思考中...' : '发送'}
          </button>
          <button className="btn" onClick={clearChat} disabled={loading || messages.length === 0}>清空对话</button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
          {PRESETS.map((p) => (
            <span key={p} className="engine-badge" style={{ cursor: 'pointer' }} onClick={() => ask(p)}>{p}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
