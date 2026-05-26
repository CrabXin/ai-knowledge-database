// 应用根组件：管理登录态与左侧菜单导航（左菜单 + 右内容布局）。
import { useState } from 'react'
import Login from './components/Login'
import CrawlerSettings from './pages/CrawlerSettings'
import Analysis from './pages/Analysis'
import AiQa from './pages/AiQa'
import UserManagement from './pages/UserManagement'

const ROLE_LABEL = { superadmin: '超级用户', admin: '管理员', user: '普通用户' }

// 根据角色生成左侧菜单：管理员/超级用户额外显示“用户管理”
function buildMenus(role) {
  const menus = [
    { key: 'crawler', label: '🕷 爬虫基本设置' },
    { key: 'analysis', label: '📊 分析结果' },
    { key: 'ai', label: '🤖 AI回答' },
  ]
  if (role === 'admin' || role === 'superadmin') {
    menus.push({ key: 'users', label: '👥 用户管理' })
  }
  return menus
}

export default function App() {
  const [user, setUser] = useState(() => {
    const u = localStorage.getItem('user')
    return u ? JSON.parse(u) : null
  })
  const [active, setActive] = useState('crawler')

  if (!user) return <Login onLogin={setUser} />

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }

  const menus = buildMenus(user.role)

  return (
    <div className="layout">
      {/* 左侧菜单 */}
      <aside className="sidebar">
        <div className="logo">
          B站数据知识库
          <small>数据分析 · AI问答系统</small>
        </div>
        {menus.map((m) => (
          <div
            key={m.key}
            className={`menu-item ${active === m.key ? 'active' : ''}`}
            onClick={() => setActive(m.key)}
          >
            {m.label}
          </div>
        ))}
        <div className="userbox">
          {user.username}
          <span className={`role-badge ${user.role === 'user' ? 'role-user' : 'role-admin'}`}>
            {ROLE_LABEL[user.role] || user.role}
          </span>
          <button className="logout-btn" onClick={logout}>退出登录</button>
        </div>
      </aside>

      {/* 右侧内容 */}
      <main className="content">
        {active === 'crawler' && <CrawlerSettings user={user} />}
        {active === 'analysis' && <Analysis />}
        {active === 'ai' && <AiQa />}
        {active === 'users' && <UserManagement />}
      </main>
    </div>
  )
}
