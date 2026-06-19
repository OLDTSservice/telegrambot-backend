import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Typography, Alert,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, StopOutlined } from '@ant-design/icons'
import { getTeamsIgnores, createTeamsIgnore, updateTeamsIgnore, deleteTeamsIgnore, getTeamsBots } from '../api'

const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function TeamsIgnorePage({ user }) {
  const [items, setItems] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [iRes, bRes] = await Promise.all([getTeamsIgnores(), getTeamsBots()])
      setItems(iRes.data)
      setBots(bRes.data)
    } catch { message.error('載入失敗') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const botName = id => bots.find(b => b.id === id)?.name || `Bot #${id}`

  const openAdd = () => { setEditingItem(null); form.resetFields(); setModalOpen(true) }
  const openEdit = item => {
    setEditingItem(item)
    form.setFieldsValue({ bot_id: item.bot_id, identifier: item.identifier, note: item.note || '' })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingItem) {
        await updateTeamsIgnore(editingItem.id, values)
        message.success('已更新')
      } else {
        await createTeamsIgnore(values)
        message.success('已新增')
      }
      setModalOpen(false)
      load()
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggle = async (item, checked) => {
    try { await updateTeamsIgnore(item.id, { is_enabled: checked }); load() }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async id => {
    try { await deleteTeamsIgnore(id); message.success('已刪除'); load() }
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
      title: '綁定機器人', dataIndex: 'bot_id', width: 160,
      render: id => botName(id),
    },
    {
      title: '新增時間', dataIndex: 'created_at', width: 160,
      render: t => new Date(t).toLocaleString('zh-TW'),
    },
    {
      title: '操作', width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />}
            onClick={() => openEdit(record)} disabled={!canEdit(user)} />
          <Popconfirm title="確定從忽略名單移除？" onConfirm={() => handleDelete(record.id)}
            disabled={!canEdit(user)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <div className="page-header">
        <h2><StopOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />Teams 忽略名單</h2>
        {canEdit(user) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增忽略帳號</Button>
        )}
      </div>

      <Alert
        type="warning" showIcon style={{ marginBottom: 16 }}
        message="在此名單中的帳號，機器人將完全忽略其傳送的訊息（不回覆關鍵字也不觸發 AI）"
        description={
          <span>
            Teams 識別碼填入使用者的 <Text code>電子郵件</Text>（如 user@company.com）或
            <Text code> AAD Object ID</Text>（可從 Azure AD 查詢）
          </span>
        }
      />

      <Table
        rowKey="id"
        dataSource={items}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: '忽略名單為空' }}
      />

      <Modal
        title={editingItem ? '編輯忽略帳號' : '新增忽略帳號'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={editingItem ? '儲存' : '新增'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="bot_id" label="綁定機器人" rules={[{ required: true, message: '請選擇機器人' }]}>
            <Select placeholder="選擇 Teams 機器人">
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item
            name="identifier"
            label="帳號識別碼（使用者 Email 或 AAD Object ID）"
            rules={[{ required: true, message: '請輸入識別碼' }]}
          >
            <Input placeholder="例如：user@company.com 或 xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </Form.Item>
          <Form.Item name="note" label="備註（選填）">
            <Input placeholder="例如：廣告帳號、已離職員工" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
