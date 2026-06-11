import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Typography,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { getRules, createRule, updateRule, deleteRule, getBots } from '../api'

const { TextArea } = Input
const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function RulesPage({ user }) {
  const [rules, setRules] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [rRes, bRes] = await Promise.all([getRules(), getBots()])
      setRules(rRes.data)
      setBots(bRes.data)
    } catch {
      message.error('載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const botName = (id) => bots.find(b => b.id === id)?.name || `Bot #${id}`

  const openAdd = () => {
    setEditingRule(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (rule) => {
    setEditingRule(rule)
    form.setFieldsValue({
      bot_id: rule.bot_id,
      keyword: rule.keyword,
      reply_message: rule.reply_message,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingRule) {
        await updateRule(editingRule.id, values)
        message.success('已更新')
      } else {
        await createRule(values)
        message.success('已新增')
      }
      setModalOpen(false)
      load()
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggle = async (rule, checked) => {
    try {
      await updateRule(rule.id, { is_enabled: checked })
      load()
    } catch {
      message.error('切換失敗')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteRule(id)
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
      width: 70,
      render: (val, record) => (
        <Switch checked={val} size="small"
          onChange={checked => handleToggle(record, checked)}
          disabled={!canEdit(user)} />
      ),
    },
    {
      title: '關鍵字規則',
      dataIndex: 'keyword',
      render: kw => <Text code>{kw}</Text>,
    },
    {
      title: '回覆訊息',
      dataIndex: 'reply_message',
      ellipsis: true,
      render: msg => <Text style={{ color: '#555' }}>{msg}</Text>,
    },
    {
      title: '綁定機器人',
      dataIndex: 'bot_id',
      width: 160,
      render: id => botName(id),
    },
    {
      title: '操作',
      width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />}
            onClick={() => openEdit(record)} disabled={!canEdit(user)} />
          <Popconfirm title="確定刪除此規則？" onConfirm={() => handleDelete(record.id)}
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
        <h2>關鍵字自動回覆規則</h2>
        {canEdit(user) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
            新增規則
          </Button>
        )}
      </div>

      <Table
        rowKey="id"
        dataSource={rules}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: '尚未設定任何關鍵字規則' }}
      />

      <Modal
        title={editingRule ? '編輯規則' : '新增規則'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={editingRule ? '儲存' : '新增'}
        cancelText="取消"
        width={520}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="bot_id" label="綁定機器人" rules={[{ required: true, message: '請選擇機器人' }]}>
            <Select placeholder="選擇機器人">
              {bots.map(b => (
                <Select.Option key={b.id} value={b.id}>
                  {b.name}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="keyword" label="關鍵字規則（包含此文字即觸發）"
            rules={[{ required: true, message: '請輸入關鍵字' }]}>
            <Input placeholder="例如：你好、優惠、價格" />
          </Form.Item>
          <Form.Item name="reply_message" label="自動回覆訊息"
            rules={[{ required: true, message: '請輸入回覆內容' }]}>
            <TextArea rows={4} placeholder="輸入機器人要回覆的訊息內容" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
