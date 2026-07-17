import React, { useEffect, useState } from 'react'
import { Card, Select, Switch, Table, Tag, Typography, message, Space, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { getBots, updateBot, getWhitelistLogs } from '../api'

const { Text } = Typography

function statusTag(status) {
  return status === 'success'
    ? <Tag color="green">成功</Tag>
    : <Tag color="red">失敗</Tag>
}

const columns = [
  { title: '群組名稱', dataIndex: 'chat_name', key: 'chat_name', ellipsis: true },
  { title: '廠商名稱', dataIndex: 'vendor_name', key: 'vendor_name', width: 100 },
  {
    title: 'IP 列表',
    dataIndex: 'ip_list',
    key: 'ip_list',
    render: (v) => (
      <span style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>{v}</span>
    ),
  },
  { title: '狀態', dataIndex: 'status', key: 'status', width: 80, render: statusTag },
  {
    title: '時間',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 150,
    render: (v) => new Date(v).toLocaleString('zh-TW'),
  },
]

export default function WhitelistPage({ user }) {
  const canEdit = user?.role === 'superadmin' || user?.role === 'editor'
  const [bots, setBots] = useState([])
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [whitelistEnabled, setWhitelistEnabled] = useState(false)
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getBots().then(r => {
      setBots(r.data)
      if (r.data.length > 0) {
        setSelectedBotId(r.data[0].id)
        setWhitelistEnabled(!!r.data[0].whitelist_enabled)
      }
    })
  }, [])

  useEffect(() => {
    if (selectedBotId) fetchLogs()
  }, [selectedBotId])

  const handleBotChange = (id) => {
    setSelectedBotId(id)
    const bot = bots.find(b => b.id === id)
    setWhitelistEnabled(!!bot?.whitelist_enabled)
  }

  const handleToggle = async (checked) => {
    try {
      await updateBot(selectedBotId, { whitelist_enabled: checked })
      setWhitelistEnabled(checked)
      message.success(checked ? '白名單自動處理已啟用' : '白名單自動處理已關閉')
    } catch {
      message.error('切換失敗')
    }
  }

  const fetchLogs = async () => {
    if (!selectedBotId) return
    setLoading(true)
    try {
      const r = await getWhitelistLogs(selectedBotId, 50)
      setLogs(r.data)
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
              {bots.map(b => (
                <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>
              ))}
            </Select>
          </Space>
          <Space>
            <Text strong>自動白名單處理：</Text>
            <Switch
              checked={whitelistEnabled}
              onChange={handleToggle}
              disabled={!canEdit || !selectedBotId}
              checkedChildren="啟用"
              unCheckedChildren="關閉"
            />
            {whitelistEnabled
              ? <Tag color="green">偵測到白名單請求將自動添加</Tag>
              : <Tag color="default">目前關閉（預設）</Tag>
            }
          </Space>
          <Button icon={<ReloadOutlined />} size="small" onClick={fetchLogs}>重新整理</Button>
        </Space>
      </Card>

      {/* 說明 */}
      <Card size="small" bodyStyle={{ padding: '10px 16px', background: '#fffbe6', border: '1px solid #ffe58f' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          啟用後，當群組訊息包含 <Text code>BO IP</Text> / <Text code>whitelist BO IP</Text> / <Text code>加白后台IP</Text> 等關鍵字，
          機器人會自動解析廠商代碼（Username 第一段）與 IP，登入後台網站新增白名單，並回覆「已添加完畢」。
          API IP 請求不在處理範圍內。
        </Text>
      </Card>

      {/* 最近 10 筆記錄 */}
      <Card title="最近 50 筆白名單處理記錄">
        <Table
          dataSource={logs}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          size="small"
          locale={{ emptyText: '尚無記錄' }}
        />
      </Card>
    </div>
  )
}
