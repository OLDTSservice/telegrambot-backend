// 後端存的是 UTC naive 時間字串（無時區標示），瀏覽器預設會誤判為本機時區，
// 這裡統一補上 Z 視為 UTC，再固定轉換為台灣時間（Asia/Taipei, UTC+8）顯示。
function toDate(v) {
  if (!v) return null
  const s = typeof v === 'string' && !/Z|[+-]\d\d:?\d\d$/.test(v) ? v + 'Z' : v
  return new Date(s)
}

export function formatDateTime(v) {
  const d = toDate(v)
  if (!d) return ''
  return d.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })
}

export function formatDate(v) {
  const d = toDate(v)
  if (!d) return ''
  return d.toLocaleDateString('zh-TW', { timeZone: 'Asia/Taipei' })
}

export function formatTime(v, opts = { hour: '2-digit', minute: '2-digit' }) {
  const d = toDate(v)
  if (!d) return ''
  return d.toLocaleTimeString('zh-TW', { timeZone: 'Asia/Taipei', ...opts })
}

export function formatMonthDay(v) {
  const d = toDate(v)
  if (!d) return ''
  return d.toLocaleDateString('zh-TW', { timeZone: 'Asia/Taipei', month: 'short', day: 'numeric' })
}

// 是否為台灣時區的「今天」
export function isTaipeiToday(v) {
  const d = toDate(v)
  if (!d) return false
  const fmt = (date) => date.toLocaleDateString('sv-SE', { timeZone: 'Asia/Taipei' })
  return fmt(d) === fmt(new Date())
}
