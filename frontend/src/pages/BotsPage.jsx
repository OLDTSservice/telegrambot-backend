import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Space,
  Popconfirm, message, Tag, Typography, Card,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, RobotOutlined } from '@ant-design/icons'
import { getBots, createBot, updateBot, deleteBot } from '../api'

const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function BotsPage({ user }) {
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingBot, setEditingBot] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const res = await getBots()
      setBots(res.data)
    } catch {
      message.error('載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openAdd = () => {
    setEditingBot(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (bot) => {
    setEditingBot(bot)
    form.setFieldsValue({ name: bot.name, token: bot.token })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingBot) {
        await updateBot(editingBot.id, values)
        message.success('已更新')
      } else {
        await createBot(values)
        message.success('已新增')
      }
      setModalOpen(false)
      load()
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggle = async (bot, checked) => {
    try {
      await updateBot(bot.id, { is_enabled: checked })
      message.success(checked ? '已啟用' : '已停用')
      load()
    } catch {
      message.error('切換失敗')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteBot(id)
      message.success('已刪除')
      load()
    } catch {
      message.error('刪除失敗')
    }
  }

  const columns = [
    {
      title: '啟用',
      dataIndex: 'is_enabled',
      width: 80,
      render: (val, record) => (
        <Switch
          checked={val}
          onChange={checked => handleToggle(record, checked)}
          disabled={!canEdit(user)}
          size="small"
        />
      ),
    },
    {
      title: '機器人名稱',
      dataIndex: 'name',
      render: (name, record) => (
        <Space>
          <RobotOutlined style={{ color: record.is_enabled ? '#52c41a' : '#bbb' }} />
          <Text strong>{name}</Text>
          {record.is_enabled && <Tag color="green" style={{ fontSize: 11 }}>運行中</Tag>}
        </Space>
      ),
    },
    {
      title: 'Token',
      dataIndex: 'token',
      ellipsis: true,
      render: token => (
        <Text code style={{ fontSize: 12 }}>{token.slice(0, 20)}…</Text>
      ),
    },
    {
      title: '建立時間',
      dataIndex: 'created_at',
      width: 160,
      render: t => new Date(t).toLocaleString('zh-TW'),
    },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Space>
          <Button
            size="small" icon={<EditOutlined />}
            onClick={() => openEdit(record)}
            disabled={!canEdit(user)}
          />
          <Popconfirm title="確定要刪除此機器人？" onConfirm={() => handleDelete(record.id)}
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
        <h2>Telegram 機器人管理</h2>
        {canEdit(user) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
            新增機器人
          </Button>
        )}
      </div>

      <Table
        rowKey="id"
        dataSource={bots}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: '尚未新增任何機器人' }}
      />

      <Modal
        title={editingBot ? '編輯機器人' : '新增機器人'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={editingBot ? '儲存' : '新增'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="機器人名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
            <Input placeholder="例如：客服機器人" />
          </Form.Item>
          <Form.Item name="token" label="Telegram Bot Token" rules={[{ required: true, message: '請輸入 Token' }]}>
            <Input.Password placeholder="從 @BotFather 取得的 Token" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
