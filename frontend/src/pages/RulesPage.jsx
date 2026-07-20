import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Typography, Empty,
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
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    try {
      const bRes = await getBots()
      setBots(bRes.data)
    } catch {
      message.error('載入失敗')
    }
  }

  const loadRules = async (botId) => {
    setLoading(true)
    try {
      const rRes = await getRules({ bot_id: botId })
      setRules(rRes.data)
    } catch {
      message.error('載入規則失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleBotChange = (botId) => {
    setSelectedBotId(botId)
    loadRules(botId)
  }

  const openAdd = () => {
    setEditingRule(null)
    form.resetFields()
    form.setFieldsValue({ bot_id: selectedBotId })
    setModalOpen(true)
  }

  const openEdit = (rule) => {
    setEditingRule(rule)
    form.setFieldsValue({
      bot_id: rule.bot_id,
      keyword: rule.keyword,
      reply_message: rule.reply_message,
      reply_message_en: rule.reply_message_en || '',
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
      if (selectedBotId) loadRules(selectedBotId)
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggle = async (rule, checked) => {
    try {
      await updateRule(rule.id, { is_enabled: checked })
      if (selectedBotId) loadRules(selectedBotId)
    } catch {
      message.error('切換失敗')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteRule(id)
      message.success('已刪除')
      if (selectedBotId) loadRules(selectedBotId)
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
      title: '中文回覆',
      dataIndex: 'reply_message',
      ellipsis: true,
      render: msg => <Text style={{ color: '#555' }}>{msg}</Text>,
    },
    {
      title: '英文回覆',
      dataIndex: 'reply_message_en',
      ellipsis: true,
      render: msg => msg
        ? <Text style={{ color: '#555' }}>{msg}</Text>
        : <Text type="secondary">（未設定，英文問題套用中文回覆）</Text>,
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
      <div className="page-header" style={{ marginBottom: 16 }}>
        <h2>關鍵字自動回覆規則</h2>
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
              新增規則
            </Button>
          )}
        </Space>
      </div>

      {!selectedBotId ? (
        <Empty description="請先選擇機器人" style={{ padding: 48 }} />
      ) : (
        <Table
          rowKey="id"
          dataSource={rules}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '此機器人尚未設定任何關鍵字規則' }}
        />
      )}

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
          <Form.Item name="reply_message" label="中文回覆訊息（預設）"
            rules={[{ required: true, message: '請輸入回覆內容' }]}>
            <TextArea rows={4} placeholder="輸入機器人要回覆的訊息內容（中文問題或未設英文時使用）" />
          </Form.Item>
          <Form.Item name="reply_message_en" label="英文回覆訊息（選填）"
            extra="純英文問題時改用此內容；未填則一律回覆上方中文版本">
            <TextArea rows={4} placeholder="English reply for non-Chinese messages" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
