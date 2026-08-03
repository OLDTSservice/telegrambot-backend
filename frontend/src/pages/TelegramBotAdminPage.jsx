import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Typography, Alert, Empty,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { getTelegramBotAdmins, createTelegramBotAdmin, updateTelegramBotAdmin, deleteTelegramBotAdmin, getBots } from '../api'
import { formatDateTime } from '../utils/datetime'

const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function TelegramBotAdminPage({ user }) {
  const [items, setItems] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    try {
      const bRes = await getBots()
      setBots(bRes.data)
    } catch { message.error('載入失敗') }
  }

  const loadItems = async (botId) => {
    setLoading(true)
    try {
      const iRes = await getTelegramBotAdmins({ bot_id: botId })
      setItems(iRes.data)
    } catch { message.error('載入管理員名單失敗') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleBotChange = (botId) => {
    setSelectedBotId(botId)
    loadItems(botId)
  }

  const openAdd = () => {
    setEditingItem(null)
    form.resetFields()
    form.setFieldsValue({ bot_id: selectedBotId })
    setModalOpen(true)
  }
  const openEdit = item => {
    setEditingItem(item)
    form.setFieldsValue({ bot_id: item.bot_id, identifier: item.identifier, note: item.note || '' })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingItem) {
        await updateTelegramBotAdmin(editingItem.id, values)
        message.success('已更新')
      } else {
        await createTelegramBotAdmin(values)
        message.success('已新增')
      }
      setModalOpen(false)
      if (selectedBotId) loadItems(selectedBotId)
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggle = async (item, checked) => {
    try { await updateTelegramBotAdmin(item.id, { is_enabled: checked }); if (selectedBotId) loadItems(selectedBotId) }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async id => {
    try { await deleteTelegramBotAdmin(id); message.success('已刪除'); if (selectedBotId) loadItems(selectedBotId) }
    catch { message.error('刪除失敗') }
  }

  const columns = [
    {
      title: '啟用', dataIndex: 'is_enabled', width: 70,
      render: (val, record) => (
        <Switch checked={val} size="small"
          onChange={checked => handleToggle(record, checked)}
          disabled={!canEdit(user)} />
      ),
    },
    {
      title: '帳號識別碼', dataIndex: 'identifier',
      render: v => <Text code>{v}</Text>,
    },
    {
      title: '備註', dataIndex: 'note',
      render: v => <Text type="secondary">{v || '—'}</Text>,
    },
    {
      title: '新增時間', dataIndex: 'created_at', width: 160,
      render: t => formatDateTime(t),
    },
    {
      title: '操作', width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />}
            onClick={() => openEdit(record)} disabled={!canEdit(user)} />
          <Popconfirm title="確定從管理員名單移除？" onConfirm={() => handleDelete(record.id)}
            disabled={!canEdit(user)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <h2><SafetyCertificateOutlined style={{ marginRight: 8, color: '#1677ff' }} />機器人管理員名單</h2>
        <Space>
          <Select
            style={{ width: 200 }}
            placeholder="選擇機器人"
            value={selectedBotId}
            onChange={handleBotChange}
          >
            {bots.map(b => (
              <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>
            ))}
          </Select>
          {canEdit(user) && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openAdd} disabled={!selectedBotId}>
              新增管理員
            </Button>
          )}
        </Space>
      </div>

      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="名單內的帳號可在群組中「回覆」機器人自己發送的訊息，並輸入 收回／撤回／undo／recall 來刪除該則訊息"
        description={
          <span>
            Telegram 識別碼填入 <Text code>@username</Text>（用戶名稱）或
            <Text code> 數字 user_id</Text>（可透過 @userinfobot 查詢）。
            非名單內的成員即使打出相同指令也不會有任何反應。
          </span>
        }
      />

      {!selectedBotId ? (
        <Empty description="請先選擇機器人" style={{ padding: 48 }} />
      ) : (
        <Table
          rowKey="id"
          dataSource={items}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '此機器人尚未設定任何管理員' }}
        />
      )}

      <Modal
        title={editingItem ? '編輯管理員' : '新增管理員'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={editingItem ? '儲存' : '新增'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="bot_id" label="綁定機器人" rules={[{ required: true, message: '請選擇機器人' }]}>
            <Select placeholder="選擇 Telegram 機器人">
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item
            name="identifier"
            label="帳號識別碼（@username 或 數字 user_id）"
            rules={[{ required: true, message: '請輸入識別碼' }]}
          >
            <Input placeholder="例如：@johndoe 或 123456789" />
          </Form.Item>
          <Form.Item name="note" label="備註（選填）">
            <Input placeholder="例如：客服主管、值班人員" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
