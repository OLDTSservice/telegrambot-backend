import React, { useEffect, useState } from 'react'
import {
  Card, Select, Switch, Table, Tag, Typography, message, Space, Button, Empty,
  Form, Input, InputNumber,
} from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { getBots, updateBot, getNetwinLogs, getNetwinStats } from '../api'
import { formatDateTime } from '../utils/datetime'

const { Text } = Typography

const OUTCOME_TAG = {
  auto_replied: { color: 'green', label: '自動回覆' },
  no_account: { color: 'default', label: '擷取不到帳號' },
  zero_match: { color: 'orange', label: '查無此人' },
  multi_match: { color: 'orange', label: '比對到多筆' },
  over_threshold: { color: 'red', label: '超過門檻' },
  null_netwin: { color: 'red', label: '淨值查詢失敗' },
  api_error: { color: 'red', label: 'API 呼叫失敗' },
}

function outcomeTag(outcome) {
  const cfg = OUTCOME_TAG[outcome] || { color: 'default', label: outcome }
  return <Tag color={cfg.color}>{cfg.label}</Tag>
}

const logColumns = [
  { title: '群組名稱', dataIndex: 'chat_name', key: 'chat_name', ellipsis: true },
  {
    title: '擷取到的帳號', dataIndex: 'extracted_account', key: 'extracted_account', width: 170,
    render: (v) => <span style={{ fontFamily: 'monospace' }}>{v || '-'}</span>,
  },
  {
    title: '比對筆數', dataIndex: 'match_count', key: 'match_count', width: 90,
    render: (v) => (v == null ? '-' : v),
  },
  {
    title: '近2日淨值(THB)', dataIndex: 'netwin_2d_thb', key: 'netwin_2d_thb', width: 130,
    render: (v) => (v == null ? '-' : v.toLocaleString()),
  },
  { title: '結果', dataIndex: 'outcome', key: 'outcome', width: 110, render: outcomeTag },
  {
    title: '時間', dataIndex: 'created_at', key: 'created_at', width: 150,
    render: (v) => formatDateTime(v),
  },
]

const statColumns = [
  { title: '群組名稱', dataIndex: 'chat_name', key: 'chat_name', ellipsis: true },
  {
    title: '查詢後回覆次數', dataIndex: 'replied_count', key: 'replied_count', width: 140,
    render: (v) => <Text strong style={{ color: '#52c41a' }}>{v}</Text>,
  },
  {
    title: '未查詢的次數', dataIndex: 'not_queried_count', key: 'not_queried_count', width: 130,
    render: (v) => <Text style={{ color: '#faad14' }}>{v}</Text>,
  },
]

export default function NetwinPage({ user }) {
  const canEdit = user?.role === 'superadmin' || user?.role === 'editor'
  const [bots, setBots] = useState([])
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [enabled, setEnabled] = useState(false)
  const [form] = Form.useForm()
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getBots().then((r) => setBots(r.data))
  }, [])

  useEffect(() => {
    if (selectedBotId) fetchAll()
  }, [selectedBotId])

  const handleBotChange = (id) => {
    setSelectedBotId(id)
    const bot = bots.find((b) => b.id === id)
    setEnabled(!!bot?.netwin_query_enabled)
    form.setFieldsValue({
      netwin_key_id: bot?.netwin_key_id || '',
      netwin_api_key: bot?.netwin_api_key || '',
      netwin_api_base_url: bot?.netwin_api_base_url || '',
      netwin_threshold: bot?.netwin_threshold ?? 5000,
      netwin_reply_zh: bot?.netwin_reply_zh || '',
      netwin_reply_en: bot?.netwin_reply_en || '',
    })
  }

  const handleToggle = async (checked) => {
    try {
      await updateBot(selectedBotId, { netwin_query_enabled: checked })
      setEnabled(checked)
      setBots((prev) => prev.map((b) => (b.id === selectedBotId ? { ...b, netwin_query_enabled: checked } : b)))
      message.success(checked ? '查輸贏回覆已啟用' : '查輸贏回覆已關閉')
    } catch {
      message.error('切換失敗')
    }
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      await updateBot(selectedBotId, values)
      setBots((prev) => prev.map((b) => (b.id === selectedBotId ? { ...b, ...values } : b)))
      message.success('設定已儲存')
    } catch (err) {
      if (err?.errorFields) return
      message.error('儲存失敗')
    } finally {
      setSaving(false)
    }
  }

  const fetchAll = async () => {
    if (!selectedBotId) return
    setLoading(true)
    try {
      const [logRes, statRes] = await Promise.all([
        getNetwinLogs(selectedBotId, 50),
        getNetwinStats(selectedBotId),
      ])
      setLogs(logRes.data)
      setStats(statRes.data)
    } catch {
      message.error('載入記錄失敗')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 頂部控制列 */}
      <Card size="small" bodyStyle={{ padding: '10px 16px' }}>
        <Space size={24} wrap>
          <Space>
            <Text strong>機器人：</Text>
            <Select style={{ width: 200 }} value={selectedBotId} onChange={handleBotChange}
              placeholder="選擇機器人">
              {bots.map((b) => (
                <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>
              ))}
            </Select>
          </Space>
          <Space>
            <Text strong>查輸贏回覆：</Text>
            <Switch
              checked={enabled}
              onChange={handleToggle}
              disabled={!canEdit || !selectedBotId}
              checkedChildren="啟用"
              unCheckedChildren="關閉"
            />
            {enabled
              ? <Tag color="green">偵測到查輸贏請求將自動判斷回覆</Tag>
              : <Tag color="default">目前關閉（預設）</Tag>}
          </Space>
          <Button icon={<ReloadOutlined />} size="small" onClick={fetchAll} disabled={!selectedBotId}>
            重新整理
          </Button>
        </Space>
      </Card>

      {!selectedBotId ? (
        <Card>
          <Empty description="請先選擇機器人" style={{ padding: 48 }} />
        </Card>
      ) : (
        <>
          {/* 說明 */}
          <Card size="small" bodyStyle={{ padding: '10px 16px', background: '#fffbe6', border: '1px solid #ffe58f' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              啟用後，當群組訊息偵測到廠商在詢問「這個玩家/這筆下注或贏分是否正常」時，機器人會先呼叫 tjadmin
              外部客服 API 查詢該玩家近2日淨值（<Text code>netwin_2d_thb</Text>）；只有查到「唯一一位玩家」且淨值低於下方門檻時，
              才會直接依固定內容自動回覆，其餘情況（查無此人、比對到多筆、超過門檻、查詢失敗、擷取不到帳號）一律跳過知識庫、直接轉人工。
            </Text>
          </Card>

          {/* API 設定與回覆內容 */}
          <Card title="API 設定與自動回覆內容">
            <Form form={form} layout="vertical">
              <Form.Item name="netwin_key_id" label="tjadmin API Key ID">
                <Input placeholder="金鑰前24字元識別段" disabled={!canEdit} />
              </Form.Item>
              <Form.Item name="netwin_api_key" label="tjadmin API 完整金鑰">
                <Input.Password placeholder="64字元完整金鑰（機密，僅產生當下顯示一次，請向平台人員索取）" disabled={!canEdit} />
              </Form.Item>
              <Form.Item name="netwin_api_base_url" label="tjadmin API 網域">
                <Input placeholder="例如：https://xxx.example.com" disabled={!canEdit} />
              </Form.Item>
              <Form.Item name="netwin_threshold" label="淨值門檻（netwin_2d_thb 低於此值才自動回覆）">
                <InputNumber style={{ width: 200 }} disabled={!canEdit} />
              </Form.Item>
              <Form.Item name="netwin_reply_zh" label="自動回覆固定內容（中文）">
                <Input.TextArea rows={4} disabled={!canEdit} />
              </Form.Item>
              <Form.Item name="netwin_reply_en" label="自動回覆固定內容（英文）">
                <Input.TextArea rows={4} disabled={!canEdit} />
              </Form.Item>
              {canEdit && (
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
                  儲存設定
                </Button>
              )}
            </Form>
          </Card>

          {/* 依群組統計 */}
          <Card title="依群組統計">
            <Table
              dataSource={stats}
              columns={statColumns}
              rowKey="chat_id"
              loading={loading}
              pagination={false}
              size="small"
              locale={{ emptyText: '尚無統計資料' }}
            />
          </Card>

          {/* 最近記錄 */}
          <Card title="最近 50 筆處理記錄">
            <Table
              dataSource={logs}
              columns={logColumns}
              rowKey="id"
              loading={loading}
              pagination={false}
              size="small"
              locale={{ emptyText: '尚無記錄' }}
            />
          </Card>
        </>
      )}
    </div>
  )
}
