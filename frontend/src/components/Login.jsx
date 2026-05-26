// 登录页：调用 /api/login，成功后保存 token 与用户信息。
import { useState } from 'react'
import api from '../api'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    setLoading(true)
    try {
      const { data } = await api.post('/login', { username, password })
      localStorage.setItem('token', data.token)
      const user = { username: data.username, role: data.role }
      localStorage.setItem('user', JSON.stringify(user))
      onLogin(user)
    } catch (e) {
      setErr(e.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h2>B站数据分析与AI知识库</h2>
        <div className="sub">多源数据采集 · 挖掘分析 · 本地大模型问答</div>
        {err && <div className="err">{err}</div>}
        <input placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input type="password" placeholder="密码" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button disabled={loading}>{loading ? '登录中...' : '登 录'}</button>
        <div className="login-tip">
          管理员：admin / admin123（可采集数据）<br />
          普通用户：user / user123（仅查看分析与问答）
        </div>
      </form>
    </div>
  )
}
