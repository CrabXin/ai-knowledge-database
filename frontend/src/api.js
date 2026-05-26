// 统一的后端 API 封装：自动附带登录 Token，统一处理 401。
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 请求拦截：附带 Bearer Token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：401 时清除登录态并刷新到登录页
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.reload()
    }
    return Promise.reject(error)
  }
)

export default api
