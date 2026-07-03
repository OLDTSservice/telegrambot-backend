import React, { useEffect, useRef, useState } from 'react'
import {
  Select, Switch, Card, Badge, Button, Input, Tooltip, Popconfirm,
  message, Typography, Tag, Space, Empty, Spin
} from 'antd'
import {
  SendOutlined, EditOutlined, CheckOutlined, CloseOutlined,
  ReloadOutlined, RobotOutlined, UserOutlined
} from '@ant-design/icons'
import {
  getBots, updateBot,
  getLiveGroups, getLiveMessages, markLiveRead,
  liveSendMessage, updatePendingReply, sendPendingReply, discardPendingReply,
} from '../api'

const { Text } = Typography
const { TextArea } = Input
const POLL_MS = 4000

function timeStr(ts) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

function dateStr(ts) {
  const d = new Date(ts)
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return '今天'
  return d.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' })
}

// ── 訊息氣泡 ─────────────────────────────────────────────────────────────
function MessageBubble({ msg, onSendPending, onDiscardPending, onEditPending }) {
  const isAdmin = msg.is_from_admin
  const pending = msg.pending_reply
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState('')

  const startEdit = () => { setEditText(pending.reply_text); setEditMode(true) }
  const cancelEdit = () => setEditMode(false)
  const saveEdit = async () => {
    await onEditPending(pending.id, editText)
    setEditMode(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isAdmin ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
      {!isAdmin && (
        <Text type="secondary" style={{ fontSize: 11, marginBottom: 2, marginLeft: 4 }}>
          {msg.sender_name || '使用者'} · {timeStr(msg.created_at)}
        </Text>
      )}
      {isAdmin && (
        <Text type="secondary" style={{ fontSize: 11, marginBottom: 2, marginRight: 4 }}>
          {timeStr(msg.created_at)}
        </Text>
      )}
      <div style={{
        maxWidth: '72%',
        background: isAdmin ? '#1677ff' : '#f0f0f0',
        color: isAdmin ? '#fff' : '#222',
        borderRadius: isAdmin ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        padding: '8px 14px',
        fontSize: 14,
        lineHeight: 1.6,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {msg.text}
      </div>

      {/* 待發送回覆 */}
      {pending && pending.status === 'pending' && (
        <div style={{
          marginTop: 6, maxWidth: '72%', border: '1.5px dashed #faad14',
          borderRadius: 10, padding: '8px 12px', background: '#fffbe6',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <RobotOutlined style={{ color: '#faad14' }} />
            <Tag color="gold" style={{ margin: 0 }}>待發送回覆</Tag>
          </div>
          {/* 引用原始問題 */}
          <div style={{
            borderLeft: '3px solid #faad14', paddingLeft: 8, marginBottom: 8,
            color: '#888', fontSize: 12, whiteSpace: 'pre-wrap',
            overflow: 'hidden', maxHeight: 48,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
          }}>
            ↩ {msg.sender_name || '使用者'}：{msg.text}
          </div>
          {editMode ? (
            <>
              <TextArea rows={3} value={editText} onChange={e => setEditText(e.target.value)} style={{ marginBottom: 6 }} />
              <Space>
                <Button size="small" type="primary" icon={<CheckOutlined />} onClick={saveEdit}>儲存</Button>
                <Button size="small" icon={<CloseOutlined />} onClick={cancelEdit}>取消</Button>
              </Space>
            </>
          ) : (
            <>
              <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', marginBottom: 8 }}>{pending.reply_text}</div>
              <Space>
                <Button size="small" type="primary" icon={<SendOutlined />}
                  onClick={() => onSendPending(pending.id)}>發送</Button>
                <Button size="small" icon={<EditOutlined />} onClick={startEdit}>編輯</Button>
                <Popconfirm title="確定捨棄此回覆？" onConfirm={() => onDiscardPending(pending.id)}>
                  <Button size="small" danger icon={<CloseOutlined />}>捨棄</Button>
                </Popconfirm>
              </Space>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── 主頁面 ────────────────────────────────────────────────────────────────
export default function TelegramLivePage({ user }) {
  const canEdit = user?.role === 'superadmin' || user?.role === 'editor'

  const [bots, setBots] = useState([])
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [isManaged, setIsManaged] = useState(false)
  const [groups, setGroups] = useState([])
  const [selectedChatId, setSelectedChatId] = useState(null)
  // 同步 ref，讓 setInterval closure 永遠讀到最新值
  useEffect(() => { selectedChatIdRef.current = selectedChatId }, [selectedChatId])
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const messagesEndRef = useRef(null)
  const pollRef = useRef(null)
  const selectedChatIdRef = useRef(null)  // 供 setInterval closure 讀取最新值

  // 載入機器人列表
  useEffect(() => {
    getBots().then(r => {
      setBots(r.data)
      if (r.data.length > 0) {
        setSelectedBotId(r.data[0].id)
        setIsManaged(!!r.data[0].is_managed)
      }
    })
  }, [])

  // 切換機器人時更新管控狀態
  const handleBotChange = (id) => {
    setSelectedBotId(id)
    setSelectedChatId(null)
    setMessages([])
    const bot = bots.find(b => b.id === id)
    setIsManaged(!!bot?.is_managed)
  }

  // 切換管控總開關
  const handleManagedToggle = async (checked) => {
    if (!selectedBotId) return
    try {
      await updateBot(selectedBotId, { is_managed: checked })
      setIsManaged(checked)
      message.success(checked ? '管控模式已啟用' : '管控模式已關閉')
    } catch {
      message.error('切換失敗')
    }
  }

  // 輪詢：更新群組列表，並對正在查看的群組即時清除未讀
  const fetchGroups = async (currentChatId) => {
    if (!selectedBotId) return
    try {
      const r = await getLiveGroups(selectedBotId)
      const chatId = currentChatId ?? selectedChatId
      setGroups(r.data.map(g =>
        g.chat_id === chatId ? { ...g, unread_count: 0 } : g
      ))
    } catch { /* ignore */ }
  }

  // 輪詢：更新訊息，若正在查看該群組則自動標為已讀
  const fetchMessages = async () => {
    if (!selectedBotId || !selectedChatId) return
    try {
      const r = await getLiveMessages(selectedBotId, selectedChatId)
      setMessages(r.data)
      // 有未讀訊息時補送一次已讀（清伺服器端未讀計數）
      if (r.data.some(m => !m.is_read && !m.is_from_admin)) {
        markLiveRead(selectedBotId, selectedChatId).catch(() => {})
      }
    } catch { /* ignore */ }
  }

  // 啟動輪詢（dependency 只放 selectedBotId，避免每次選群組都重置 interval）
  useEffect(() => {
    if (!selectedBotId) return
    fetchGroups()
    const id = setInterval(() => {
      const chatId = selectedChatIdRef.current
      fetchGroups(chatId)   // 傳入當前群組 → 立即把該群組未讀歸零
      if (chatId) fetchMessages()
    }, POLL_MS)
    pollRef.current = id
    return () => clearInterval(id)
  }, [selectedBotId])

  // 選擇群組
  const handleSelectGroup = async (chatId) => {
    setSelectedChatId(chatId)
    setLoadingMsgs(true)
    try {
      const r = await getLiveMessages(selectedBotId, chatId)
      setMessages(r.data)
      await markLiveRead(selectedBotId, chatId)
      // 更新未讀數
      setGroups(prev => prev.map(g => g.chat_id === chatId ? { ...g, unread_count: 0 } : g))
    } catch { message.error('載入訊息失敗') }
    finally { setLoadingMsgs(false) }
  }

  // 自動捲到最底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 手動發送訊息
  const handleSend = async () => {
    if (!inputText.trim() || !selectedChatId) return
    setSending(true)
    try {
      await liveSendMessage({ bot_id: selectedBotId, chat_id: selectedChatId, text: inputText.trim() })
      setInputText('')
      await fetchMessages()
    } catch (e) {
      message.error(e.response?.data?.detail || '發送失敗')
    } finally { setSending(false) }
  }

  // 待發送回覆操作
  const handleSendPending = async (id) => {
    try {
      await sendPendingReply(id)
      message.success('已發送')
      await fetchMessages()
      await fetchGroups()
    } catch (e) { message.error(e.response?.data?.detail || '發送失敗') }
  }

  const handleDiscardPending = async (id) => {
    try {
      await discardPendingReply(id)
      message.success('已捨棄')
      await fetchMessages()
      await fetchGroups()
    } catch { message.error('操作失敗') }
  }

  const handleEditPending = async (id, text) => {
    try {
      await updatePendingReply(id, { reply_text: text })
      await fetchMessages()
    } catch { message.error('儲存失敗') }
  }

  const selectedGroup = groups.find(g => g.chat_id === selectedChatId)
  const pendingTotal = groups.reduce((s, g) => s + g.pending_count, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)', gap: 12 }}>
      {/* 頂部工具列 */}
      <Card size="small" bodyStyle={{ padding: '10px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Text strong>機器人：</Text>
            <Select style={{ width: 200 }} value={selectedBotId} onChange={handleBotChange}
              placeholder="選擇機器人">
              {bots.map(b => (
                <Select.Option key={b.id} value={b.id}>
                  {b.name} {!b.is_enabled && <Tag color="red" style={{ marginLeft: 4 }}>停用</Tag>}
                </Select.Option>
              ))}
            </Select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Text strong>即時管控：</Text>
            <Switch
              checked={isManaged}
              onChange={handleManagedToggle}
              disabled={!canEdit || !selectedBotId}
              checkedChildren="啟用"
              unCheckedChildren="關閉"
            />
            {isManaged && (
              <Tag color="orange">管控中 — 機器人不自動回覆</Tag>
            )}
            {pendingTotal > 0 && (
              <Tag color="gold">{pendingTotal} 則待發送</Tag>
            )}
          </div>
          <Tooltip title="重新整理">
            <Button icon={<ReloadOutlined />} size="small"
              onClick={() => { fetchGroups(); fetchMessages() }} />
          </Tooltip>
        </div>
      </Card>

      {/* 主體：聊天區 + 群組側欄 */}
      <div style={{ display: 'flex', flex: 1, gap: 12, overflow: 'hidden' }}>
        {/* 聊天區 */}
        <Card
          style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
          bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}
          title={selectedGroup
            ? <span><RobotOutlined /> {selectedGroup.chat_name}</span>
            : <Text type="secondary">請從右側選擇群組</Text>
          }
          extra={selectedGroup && (
            <Tag color={selectedGroup.chat_type === 'private' ? 'blue' : 'green'}>
              {selectedGroup.chat_type}
            </Tag>
          )}
        >
          {/* 訊息列表 */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
            {!selectedChatId ? (
              <Empty description="請從右側選擇群組" style={{ marginTop: 60 }} />
            ) : loadingMsgs ? (
              <div style={{ textAlign: 'center', paddingTop: 60 }}><Spin /></div>
            ) : messages.length === 0 ? (
              <Empty description="尚無訊息記錄" style={{ marginTop: 60 }} />
            ) : (
              <>
                {messages.map((msg, i) => {
                  const prevMsg = messages[i - 1]
                  const showDate = !prevMsg || dateStr(prevMsg.created_at) !== dateStr(msg.created_at)
                  return (
                    <div key={msg.id}>
                      {showDate && (
                        <div style={{ textAlign: 'center', margin: '8px 0' }}>
                          <Tag>{dateStr(msg.created_at)}</Tag>
                        </div>
                      )}
                      <MessageBubble
                        msg={msg}
                        onSendPending={handleSendPending}
                        onDiscardPending={handleDiscardPending}
                        onEditPending={handleEditPending}
                      />
                    </div>
                  )
                })}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* 輸入框 */}
          <div style={{ borderTop: '1px solid #f0f0f0', padding: '12px 16px', display: 'flex', gap: 8 }}>
            <TextArea
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder={selectedChatId ? '輸入訊息，Enter 發送（Shift+Enter 換行）' : '請先選擇群組'}
              disabled={!selectedChatId || !canEdit}
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{ flex: 1 }}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={handleSend}
              loading={sending} disabled={!selectedChatId || !inputText.trim() || !canEdit}>
              發送
            </Button>
          </div>
        </Card>

        {/* 群組側欄 */}
        <Card
          style={{ width: 240, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
          bodyStyle={{ padding: 0, flex: 1, overflowY: 'auto' }}
          title={<span><UserOutlined /> 群組列表</span>}
        >
          {!selectedBotId ? (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <Text type="secondary">請先選擇機器人</Text>
            </div>
          ) : groups.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <Text type="secondary">尚無訊息</Text>
            </div>
          ) : (
            groups.map(g => (
              <div
                key={g.chat_id}
                onClick={() => handleSelectGroup(g.chat_id)}
                style={{
                  padding: '10px 14px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #f5f5f5',
                  background: selectedChatId === g.chat_id ? '#e6f4ff' : 'transparent',
                  transition: 'background 0.15s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text strong ellipsis style={{ maxWidth: 140, fontSize: 13 }}>{g.chat_name}</Text>
                  <Space size={4}>
                    {g.pending_count > 0 && (
                      <Badge count={g.pending_count} color="gold" size="small" />
                    )}
                    {g.unread_count > 0 && (
                      <Badge count={g.unread_count} size="small" />
                    )}
                  </Space>
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {dateStr(g.last_message_at)} {timeStr(g.last_message_at)}
                </Text>
              </div>
            ))
          )}
        </Card>
      </div>
    </div>
  )
}
