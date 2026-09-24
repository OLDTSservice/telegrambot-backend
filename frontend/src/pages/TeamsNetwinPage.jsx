import React, { useEffect, useState } from 'react'
import { Card, Select, Switch, Table, Tag, Typography, message, Space, Button, Empty, Tooltip, Descriptions, Alert } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { getTeamsBots, updateTeamsBot, getTeamsNetwinLogs, getBots } from '../api'
import { formatDateTime } from '../utils/datetime'

const { Text } = Typography

// outcome 值與 Telegram 查輸贏回覆相同，另外多 log_only / querying
const OUTCOME_TAG = {
  auto_replied: { color: 'green', label: '符合門檻' },
  no_account: { color: 'default', label: '擷取不到帳號' },
  zero_match: { color: 'orange', label: '查無此人' },
  multi_match: { color: 'orange', label: '比對到多筆' },
  over_threshold: { color: 'red', label: '淨值超過門檻' },
  zero_netwin: { color: 'orange', label: '淨值為0（無遊玩紀錄）' },
  null_netwin: { color: 'red', label: '淨值查詢失敗' },
  api_error: { color: 'red', label: 'API 呼叫失敗／設定未完成' },
  rtp_error: { color: 'red', label: 'RTP 查詢失敗' },
  rtp_null: { color: 'orange', label: 'RTP為null（近7日無下注）' },
  over_rtp_threshold: { color: 'red', label: 'RTP 超過門檻' },
  log_only: { color: 'default', label: '只記錄' },
  querying: { color: 'blue', label: '查詢中' },
}

const MODES = [
  { value: 'log_only', label: '只記錄', desc: '只偵測並擷取帳號、寫入紀錄，不查 API、不回覆。上線前觀察誤判用。' },
  { value: 'no_reply', label: '查詢但不回覆', desc: '會查 API 並寫入完整結果，但不在群組回覆。' },
  { value: 'full', label: '全自動', desc: '查 API，淨值與 RTP 都在門檻內才延遲引用回覆；其餘結果靜默。' },
]

const columns = [
  { title: '群組名稱', dataIndex: 'chat_name', key: 'chat_name', ellipsis: true },
  { title: '發送者', dataIndex: 'sender', key: 'sender', width: 140, ellipsis: true },
  {
    title: '擷取到的帳號', dataIndex: 'extracted_account', key: 'extracted_account', width: 170,
    render: v => <span style={{ fontFamily: 'monospace' }}>{v || '-'}</span>,
  },
  { title: '比對筆數', dataIndex: 'match_count', key: 'match_count', width: 90, render: v => (v == null ? '-' : v) },
  {
    title: '近2日淨值(THB)', dataIndex: 'netwin_2d_thb', key: 'netwin_2d_thb', width: 130,
    render: v => (v == null ? '-' : v.toLocaleString()),
  },
  { title: '近7日RTP(%)', dataIndex: 'rtp', key: 'rtp', width: 110, render: v => (v == null ? '-' : v.toLocaleString()) },
  {
    title: '結果', dataIndex: 'outcome', key: 'outcome', width: 160,
    render: o => { const c = OUTCOME_TAG[o] || { color: 'default', label: o }; return <Tag color={c.color}>{c.label}</Tag> },
  },
  { title: '已回覆', dataIndex: 'reply_sent', key: 'reply_sent', width: 70, render: v => (v ? '是' : '-') },
  { title: '時間', dataIndex: 'created_at', key: 'created_at', width: 150, render: v => formatDateTime(v) },
]

const isReady = b => !!(b && b.netwin_key_id && b.netwin_api_key && b.netwin_api_base_url && b.netwin_rtp_threshold != null)

export default function TeamsNetwinPage({ user }) {
  const canEdit = user?.role === 'superadmin' || user?.role === 'editor'
  const [bots, setBots] = useState([])
  const [tgBots, setTgBots] = useState([])
  const [botId, setBotId] = useState(null)
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getTeamsBots().then(r => setBots(r.data))
    getBots().then(r => setTgBots(r.data)).catch(() => {})
  }, [])
  useEffect(() => { if (botId) fetchLogs() }, [botId])

  const bot = bots.find(b => b.id === botId)
  const enabled = !!bot?.netwin_query_enabled
  const mode = bot?.netwin_mode || 'full'
  const src = tgBots.find(b => b.id === bot?.netwin_source_bot_id)

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
    try { setLogs((await getTeamsNetwinLogs(botId, 50)).data) }
    catch { message.error('載入記錄失敗') }
    finally { setLoading(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small" bodyStyle={{ padding: '10px 16px' }}>
        <Space size={24} wrap>
          <Space>
            <Text strong>機器人：</Text>
            <Select style={{ width: 220 }} value={botId} onChange={setBotId} placeholder="選擇機器人">
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </Space>
          <Space>
            <Text strong>查輸贏回覆：</Text>
            <Switch checked={enabled} disabled={!canEdit || !botId} checkedChildren="啟用" unCheckedChildren="關閉"
              onChange={c => save({ netwin_query_enabled: c }, c ? '查輸贏回覆已啟用' : '查輸贏回覆已關閉')} />
          </Space>
          <Space>
            <Text strong>模式：</Text>
            <Select style={{ width: 150 }} value={mode} disabled={!canEdit || !botId || !enabled}
              onChange={m => save({ netwin_mode: m }, `模式已切換為「${MODES.find(x => x.value === m)?.label}」`)}
              options={MODES.map(m => ({ value: m.value, label: <Tooltip title={m.desc}>{m.label}</Tooltip> }))} />
            {enabled
              ? <Tag color={mode === 'full' ? 'green' : 'blue'}>{MODES.find(x => x.value === mode)?.desc}</Tag>
              : <Tag color="default">目前關閉（預設）</Tag>}
          </Space>
          <Button icon={<ReloadOutlined />} size="small" onClick={fetchLogs} disabled={!botId}>重新整理</Button>
        </Space>
      </Card>

      {!botId ? (
        <Card><Empty description="請先選擇機器人" style={{ padding: 48 }} /></Card>
      ) : (
        <>
          <Card size="small" bodyStyle={{ padding: '10px 16px', background: '#fffbe6', border: '1px solid #ffe58f' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              觸發關鍵字、帳號擷取規則與判斷流程和 Telegram 查輸贏回覆<strong>完全相同</strong>（共用同一份程式）；
              API 憑證、淨值／RTP 門檻、延遲秒數、回覆內容則<strong>共用下方指定的 Telegram 機器人設定</strong>，
              要修改請到「Telegram 機器人 → 查輸贏回覆」頁面。
              與 Telegram 的差異：<strong>只有淨值與 RTP 都在門檻內才會引用回覆</strong>，其餘結果（查無此人、超過門檻、
              擷取不到帳號、API 失敗等）一律靜默、只寫紀錄，不會自動發轉人工訊息。
              另外需在「機器人管理 → 群組設定」逐群開啟「查輸贏回覆」才會處理該群（預設全部關閉）。
            </Text>
          </Card>

          <Card size="small" title="共用的 Telegram 查輸贏設定">
            <Space style={{ marginBottom: 12 }}>
              <Text strong>共用來源：</Text>
              <Select style={{ width: 260 }} value={bot?.netwin_source_bot_id ?? undefined} placeholder="選擇 Telegram 機器人"
                disabled={!canEdit}
                onChange={id => save({ netwin_source_bot_id: id }, '已更新共用來源')}
                options={tgBots.map(b => ({
                  value: b.id,
                  label: <span>{b.name} {isReady(b) ? <Tag color="green">已設定</Tag> : <Tag color="red">未設定完成</Tag>}</span>,
                }))} />
            </Space>
            {!src ? (
              <Alert type="warning" showIcon message="尚未指定共用來源：開啟後偵測到的查輸贏訊息會記為「API 呼叫失敗／設定未完成」，不會查詢也不會回覆。" />
            ) : (
              <>
                {!isReady(src) && (
                  <Alert type="error" showIcon style={{ marginBottom: 12 }}
                    message="此 Telegram 機器人的 API 憑證或 RTP 門檻尚未設定完成，Teams 端將不會查詢也不會回覆。" />
                )}
                <Descriptions size="small" column={2} bordered>
                  <Descriptions.Item label="API 網域">{src.netwin_api_base_url || <Text type="danger">未設定</Text>}</Descriptions.Item>
                  <Descriptions.Item label="API 憑證">{src.netwin_key_id && src.netwin_api_key ? '已設定' : <Text type="danger">未設定</Text>}</Descriptions.Item>
                  <Descriptions.Item label="淨值門檻">{src.netwin_threshold ?? 5000}</Descriptions.Item>
                  <Descriptions.Item label="RTP 門檻">{src.netwin_rtp_threshold ?? <Text type="danger">未設定</Text>}</Descriptions.Item>
                  <Descriptions.Item label="回覆延遲">{src.netwin_reply_delay_seconds ?? 30} 秒</Descriptions.Item>
                  <Descriptions.Item label="Telegram 端開關">{src.netwin_query_enabled ? '啟用' : '關閉'}（不影響 Teams）</Descriptions.Item>
                  <Descriptions.Item label="回覆內容（中文）" span={2}>
                    <span style={{ whiteSpace: 'pre-wrap' }}>{src.netwin_reply_zh || <Text type="warning">未設定（中文訊息符合門檻時不會回覆）</Text>}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="回覆內容（英文）" span={2}>
                    <span style={{ whiteSpace: 'pre-wrap' }}>{src.netwin_reply_en || <Text type="warning">未設定（英文訊息符合門檻時不會回覆）</Text>}</span>
                  </Descriptions.Item>
                </Descriptions>
              </>
            )}
          </Card>

          <Card size="small" title="最近 50 筆處理紀錄">
            <Table rowKey="id" dataSource={logs} columns={columns} loading={loading} size="small"
              pagination={false} scroll={{ x: 1150 }} locale={{ emptyText: '尚無處理紀錄' }} />
          </Card>
        </>
      )}
    </div>
  )
}
