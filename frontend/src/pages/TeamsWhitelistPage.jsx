import React, { useEffect, useState } from 'react'
import { Card, Select, Switch, Table, Tag, Typography, message, Space, Button, Empty, Tooltip } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { getTeamsBots, updateTeamsBot, getTeamsWhitelistLogs } from '../api'
import { formatDateTime } from '../utils/datetime'

const { Text } = Typography

const STATUS = {
  success: <Tag color="green">成功</Tag>,
  failed: <Tag color="red">失敗</Tag>,
  rejected: <Tag color="orange">廠商拒絕</Tag>,
  log_only: <Tag>只記錄</Tag>,
}

const MODES = [
  { value: 'log_only', label: '只記錄', desc: '只偵測並寫入紀錄，不打後台、不回覆。上線前觀察誤判用。' },
  { value: 'no_reply', label: '加白但不回覆', desc: '會呼叫後台加白並寫紀錄，但不在群組回覆。' },
  { value: 'full', label: '全自動', desc: '加白 + 引用回覆 Done／拒絕訊息 + 建立工單（與 Telegram 相同）。' },
]

const columns = [
  { title: '群組名稱', dataIndex: 'chat_name', key: 'chat_name', ellipsis: true },
  { title: '發送者', dataIndex: 'sender', key: 'sender', width: 140, ellipsis: true },
  { title: '廠商名稱', dataIndex: 'vendor_name', key: 'vendor_name', width: 110 },
  {
    title: '代理帳號', dataIndex: 'full_username', key: 'full_username', width: 180,
    render: v => <span style={{ fontFamily: 'monospace' }}>{v || '-'}</span>,
  },
  {
    title: 'IP 列表', dataIndex: 'ip_list', key: 'ip_list',
    render: v => <span style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
  },
  { title: '狀態', dataIndex: 'status', key: 'status', width: 90, render: s => STATUS[s] || <Tag>{s}</Tag> },
  { title: '已回覆', dataIndex: 'reply_sent', key: 'reply_sent', width: 70, render: v => (v ? '是' : '-') },
  { title: '時間', dataIndex: 'created_at', key: 'created_at', width: 150, render: v => formatDateTime(v) },
]

export default function TeamsWhitelistPage({ user }) {
  const canEdit = user?.role === 'superadmin' || user?.role === 'editor'
  const [bots, setBots] = useState([])
  const [botId, setBotId] = useState(null)
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('full')
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => { getTeamsBots().then(r => setBots(r.data)) }, [])
  useEffect(() => { if (botId) fetchLogs() }, [botId])

  const handleBotChange = id => {
    setBotId(id)
    const b = bots.find(x => x.id === id)
    setEnabled(!!b?.whitelist_enabled)
    setMode(b?.whitelist_mode || 'full')
  }

  const save = async (patch, okMsg) => {
    try {
      const r = await updateTeamsBot(botId, patch)
      setBots(prev => prev.map(b => b.id === botId ? r.data : b))
      message.success(okMsg)
    } catch (e) { message.error(e.response?.data?.detail || '更新失敗') }
  }

  const fetchLogs = async () => {
    if (!botId) return
    setLoading(true)
    try { setLogs((await getTeamsWhitelistLogs(botId, 50)).data) }
    catch { message.error('載入記錄失敗') }
    finally { setLoading(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small" bodyStyle={{ padding: '10px 16px' }}>
        <Space size={24} wrap>
          <Space>
            <Text strong>機器人：</Text>
            <Select style={{ width: 220 }} value={botId} onChange={handleBotChange} placeholder="選擇機器人">
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </Space>
          <Space>
            <Text strong>自動白名單處理：</Text>
            <Switch checked={enabled} disabled={!canEdit || !botId} checkedChildren="啟用" unCheckedChildren="關閉"
              onChange={c => { setEnabled(c); save({ whitelist_enabled: c }, c ? '白名單自動處理已啟用' : '白名單自動處理已關閉') }} />
          </Space>
          <Space>
            <Text strong>模式：</Text>
            <Select style={{ width: 150 }} value={mode} disabled={!canEdit || !botId || !enabled}
              onChange={m => { setMode(m); save({ whitelist_mode: m }, `模式已切換為「${MODES.find(x => x.value === m)?.label}」`) }}
              options={MODES.map(m => ({ value: m.value, label: <Tooltip title={m.desc}>{m.label}</Tooltip> }))} />
            {enabled
              ? <Tag color={mode === 'full' ? 'green' : 'blue'}>{MODES.find(x => x.value === mode)?.desc}</Tag>
              : <Tag color="default">目前關閉（預設）</Tag>}
          </Space>
          <Button icon={<ReloadOutlined />} size="small" onClick={fetchLogs}>重新整理</Button>
        </Space>
      </Card>

      {!botId ? (
        <Card><Empty description="請先選擇機器人" style={{ padding: 48 }} /></Card>
      ) : (
        <Card size="small" title="最近 50 筆處理紀錄">
          <Table rowKey="id" dataSource={logs} columns={columns} loading={loading} size="small"
            pagination={false} scroll={{ x: 1000 }} locale={{ emptyText: '尚無處理紀錄' }} />
        </Card>
      )}
    </div>
  )
}
