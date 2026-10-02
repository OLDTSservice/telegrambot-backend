// 後台頁面權限：key 必須與後端 backend/auth.py 的 PAGE_KEYS 一致。
// 「帳號管理」不在清單內，固定只有超級管理員能使用。
export const PAGES = [
  { key: 'telegram_bots', path: '/telegram/bots', group: 'Telegram 機器人', label: '機器人管理' },
  { key: 'telegram_rules', path: '/telegram/rules', group: 'Telegram 機器人', label: '關鍵字規則' },
  { key: 'telegram_knowledge', path: '/telegram/knowledge', group: 'Telegram 機器人', label: '知識庫管理' },
  { key: 'telegram_ignores', path: '/telegram/ignores', group: 'Telegram 機器人', label: '忽略名單' },
  { key: 'telegram_bot_admins', path: '/telegram/bot-admins', group: 'Telegram 機器人', label: '機器人管理員名單' },
  { key: 'telegram_reply_stats', path: '/telegram/reply-stats', group: 'Telegram 機器人', label: '回覆工單統計' },
  { key: 'telegram_live', path: '/telegram/live', group: 'Telegram 機器人', label: '即時對話管控' },
  { key: 'telegram_whitelist', path: '/telegram/whitelist', group: 'Telegram 機器人', label: '後台白名單處理' },
  { key: 'telegram_netwin', path: '/telegram/netwin', group: 'Telegram 機器人', label: '查輸贏回覆' },
  { key: 'teams_bots', path: '/teams/bots', group: 'Teams 機器人', label: '機器人管理' },
  { key: 'teams_rules', path: '/teams/rules', group: 'Teams 機器人', label: '關鍵字規則' },
  { key: 'teams_knowledge', path: '/teams/knowledge', group: 'Teams 機器人', label: '知識庫管理' },
  { key: 'teams_ignores', path: '/teams/ignores', group: 'Teams 機器人', label: '忽略名單' },
  { key: 'teams_reply_stats', path: '/teams/reply-stats', group: 'Teams 機器人', label: '回覆工單統計' },
  { key: 'teams_whitelist', path: '/teams/whitelist', group: 'Teams 機器人', label: '後台白名單處理' },
  { key: 'teams_netwin', path: '/teams/netwin', group: 'Teams 機器人', label: '查輸贏回覆' },
  { key: 'usage_stats', path: '/stats', group: '其他', label: '使用量統計' },
]

export const PAGE_GROUPS = [...new Set(PAGES.map(p => p.group))]

export const pageByPath = path => PAGES.find(p => p.path === path)

// page_permissions 由後端 /api/auth/me 回傳實際生效的權限（超級管理員全部為 edit）
export const canViewPage = (user, key) => !!user?.page_permissions?.[key]
export const canEditPage = (user, key) => user?.page_permissions?.[key] === 'edit'

export const firstAllowedPath = user => {
  const page = PAGES.find(p => canViewPage(user, p.key))
  if (page) return page.path
  return user?.role === 'superadmin' ? '/users' : null
}

// 各頁面原本用 user.role 判斷能否編輯（superadmin / editor 可編輯）。
// 傳給頁面的 user 依「該頁」的權限換算角色，頁面本身不用改：可編輯 → editor、只能查看 → viewer。
export const pageUser = (user, key) => {
  if (!user || user.role === 'superadmin') return user
  return { ...user, role: canEditPage(user, key) ? 'editor' : 'viewer' }
}
