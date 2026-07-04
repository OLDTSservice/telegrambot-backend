import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ───────────────────────────────────────
export const login = (username, password) => {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  return api.post('/auth/login', form)
}
export const getMe = () => api.get('/auth/me')

// ── Users ──────────────────────────────────────
export const getUsers = () => api.get('/users')
export const createUser = d => api.post('/users', d)
export const updateUser = (id, d) => api.put(`/users/${id}`, d)
export const deleteUser = id => api.delete(`/users/${id}`)

// ── Bots ───────────────────────────────────────
export const getBots = () => api.get('/bots')
export const createBot = d => api.post('/bots', d)
export const updateBot = (id, d) => api.put(`/bots/${id}`, d)
export const deleteBot = id => api.delete(`/bots/${id}`)

// ── Rules ──────────────────────────────────────
export const getRules = () => api.get('/rules')
export const createRule = d => api.post('/rules', d)
export const updateRule = (id, d) => api.put(`/rules/${id}`, d)
export const deleteRule = id => api.delete(`/rules/${id}`)

// ── Knowledge ──────────────────────────────────
export const getDocs = () => api.get('/knowledge')
export const uploadDoc = formData => api.post('/knowledge', formData)
export const updateDoc = (id, d) => api.put(`/knowledge/${id}`, d)
export const deleteDoc = id => api.delete(`/knowledge/${id}`)

// ── Stats ──────────────────────────────────────
export const getStats = (days = 30) => api.get(`/stats?days=${days}`)

// ── Telegram Ignore ────────────────────────────
export const getTelegramIgnores = () => api.get('/telegram-ignores')
export const createTelegramIgnore = d => api.post('/telegram-ignores', d)
export const updateTelegramIgnore = (id, d) => api.put(`/telegram-ignores/${id}`, d)
export const deleteTelegramIgnore = id => api.delete(`/telegram-ignores/${id}`)

// ── Group Stats ────────────────────────────────
export const getTelegramGroupStats = (period, value, botId) =>
  api.get('/group-stats/telegram', { params: { period, value, bot_id: botId || undefined } })
export const getTelegramTrend = (period, value, botId) =>
  api.get('/group-stats/telegram/trend', { params: { period, value, bot_id: botId || undefined } })

// ── Telegram Live 即時對話管控 ─────────────────
export const getLiveGroups = (botId) => api.get('/telegram-live/groups', { params: { bot_id: botId } })
export const getLiveMessages = (botId, chatId) => api.get('/telegram-live/messages', { params: { bot_id: botId, chat_id: chatId } })
export const markLiveRead = (botId, chatId) => api.put('/telegram-live/read', null, { params: { bot_id: botId, chat_id: chatId } })
export const liveSendMessage = (d) => api.post('/telegram-live/send', d)
export const updatePendingReply = (id, d) => api.put(`/telegram-live/pending/${id}`, d)
export const sendPendingReply = (id) => api.post(`/telegram-live/pending/${id}/send`)
export const discardPendingReply = (id) => api.delete(`/telegram-live/pending/${id}`)
