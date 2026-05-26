// 用户管理页：管理员可新增普通用户，超级用户可新增管理员/普通用户；新建账号可直接登录。
import { useEffect, useState } from 'react'
import api from '../api'

const ROLE_LABEL = { superadmin: '超级用户', admin: '管理员', user: '普通用户' }

export default function UserManagement() {
  const [users, setUsers] = useState([])
  const [creatable, setCreatable] = useState(['user'])
  const [form, setForm] = useState({ username: '', password: '', role: 'user' })
  const [msg, setMsg] = useState(null)

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const load = async () => {
    const { data } = await api.get('/users')
    setUsers(data.users)
    setCreatable(data.creatable_roles)
    setForm((f) => ({ ...f, role: data.creatable_roles[data.creatable_roles.length - 1] }))
  }

  useEffect(() => { load() }, [])

  const submit = async () => {
    setMsg(null)
    try {
      const { data } = await api.post('/users', form)
      setMsg({ type: 'ok', text: `${data.message}（${form.username} / ${ROLE_LABEL[form.user?.role || form.role]}）` })
      setForm((f) => ({ ...f, username: '', password: '' }))
      load()
    } catch (e) {
      setMsg({ type: 'err', text: e.response?.data?.detail || '创建失败' })
    }
  }

  return (
    <div>
      <h2 className="page-title">用户管理</h2>

      <div className="card">
        <h3>新增账号</h3>
        <div className="form-row">
          <label>用户名</label>
          <input type="text" value={form.username} onChange={(e) => setField('username', e.target.value)} />
        </div>
        <div className="form-row">
          <label>密码</label>
          <input type="text" value={form.password} onChange={(e) => setField('password', e.target.value)} />
          <span className="muted">至少 5 位</span>
        </div>
        <div className="form-row">
          <label>账号角色</label>
          <select value={form.role} onChange={(e) => setField('role', e.target.value)}>
            {creatable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
          <span className="muted">
            {creatable.includes('admin') ? '超级用户可新增管理员或普通用户' : '管理员仅可新增普通用户'}
          </span>
        </div>
        <div className="form-row">
          <label></label>
          <button className="btn" onClick={submit}>创建账号</button>
        </div>
        {msg && (
          <div className={`status-box ${msg.type === 'ok' ? 'status-idle' : 'status-running'}`}>
            {msg.type === 'ok' ? '✅ ' : '⚠ '}{msg.text}
          </div>
        )}
      </div>

      <div className="card">
        <h3>现有账号（共 {users.length} 个）</h3>
        <table>
          <thead><tr><th>用户名</th><th>角色</th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username}>
                <td>{u.username}</td>
                <td>
                  <span className={`role-badge ${u.role === 'user' ? 'role-user' : 'role-admin'}`}>
                    {ROLE_LABEL[u.role] || u.role}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
