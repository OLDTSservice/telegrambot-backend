import React, { useEffect, useState } from 'react'
import { Table, Button, Switch, Modal, Form, Input, Select, Popconfirm, message, Space, Card, Typography } from 'antd'
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { getCopilotRules, createCopilotRule, updateCopilotRule, deleteCopilotRule, getCopilotBots } from '../api'

const { TextArea } = Input
const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function CopilotRulesPage({ user }) {
  const [rules, setRules] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editRule, setEditRule] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [rRes, bRes] = await Promise.all([getCopilotRules(), getCopilotBots()])
      setRules(rRes.data); setBots(bRes.data)
    } catch { message.error('載入失敗') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const botName = id => bots.find(b => b.id === id)?.name || `Bot #${id}`

  const openCreate = () => { setEditRule(null); form.resetFields(); setModalOpen(true) }
  const openEdit = rule => {
    setEditRule(rule)
    form.setFieldsValue({ bot_id: rule.bot_id, keyword: rule.keyword, reply_message: rule.reply_message })
    setModalOpen(true)
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    try {
      if (editRule) { await updateCopilotRule(editRule.id, values); message.success('已更新') }
      else { await createCopilotRule(values); message.success('已新增') }
      setModalOpen(false); load()
    } catch { message.error('儲存失敗') }
  }

  const handleToggle = async (rule, checked) => {
    try { await updateCopilotRule(rule.id, { is_enabled: checked }); load() }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async id => {
    try { await deleteCopilotRule(id); message.success('已刪除'); load() }
    catch { message.error('刪除失敗') }
  }

  const columns = [
    { title: '啟用', dataIndex: 'is_enabled', width: 70, render: (v, r) => <Switch checked={v} size="small" onChange={c => handleToggle(r, c)} disabled={!canEdit(user)} /> },
    { title: '關鍵字', dataIndex: 'keyword', render: k => <Text code>{k}</Text> },
    { title: '回覆內容', dataIndex: 'reply_message', ellipsis: true },
    { title: '機器人', dataIndex: 'bot_id', width: 160, render: id => botName(id) },
    {
      title: '操作', width: 100, render: (_, r) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} disabled={!canEdit(user)} />
          <Popconfirm title="確定刪除？" onConfirm={() => handleDelete(r.id)} disabled={!canEdit(user)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <Card>
      <div className="page-header">
        <h2>Copilot 關鍵字規則</h2>
        {canEdit(user) && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增規則</Button>}
      </div>
      <Text type="secondary" style={{ display: 'block', marginBottom: 16, fontSize: 13 }}>
        當使用者訊息包含關鍵字時，優先回覆設定的固定內容（優先於知識庫 AI 回答）。
      </Text>
      <Table rowKey="id" dataSource={rules} columns={columns} loading={loading} pagination={{ pageSize: 10 }} />

      <Modal title={editRule ? '編輯規則' : '新增關鍵字規則'} open={modalOpen}
        onOk={handleSave} onCancel={() => setModalOpen(false)} okText="儲存" cancelText="取消">
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="bot_id" label="綁定機器人" rules={[{ required: true }]}>
            <Select placeholder="選擇機器人">
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="keyword" label="關鍵字" rules={[{ required: true, message: '請輸入關鍵字' }]}>
            <Input placeholder="例：API URL、白名單、RTP" />
          </Form.Item>
          <Form.Item name="reply_message" label="回覆內容" rules={[{ required: true, message: '請輸入回覆內容' }]}>
            <TextArea rows={4} placeholder="使用者詢問關鍵字時的固定回覆" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
