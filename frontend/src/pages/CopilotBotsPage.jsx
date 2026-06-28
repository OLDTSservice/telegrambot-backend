import React, { useEffect, useState } from 'react'
import { Table, Button, Switch, Modal, Form, Input, Popconfirm, message, Card, Typography, Tag, Space, Tooltip } from 'antd'
import { PlusOutlined, DeleteOutlined, EditOutlined, CopyOutlined, RobotOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { getCopilotBots, createCopilotBot, updateCopilotBot, deleteCopilotBot } from '../api'

const { Text, Paragraph } = Typography
const BACKEND_URL = 'https://tg-admin-backend-rm99.onrender.com'
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function CopilotBotsPage({ user }) {
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editBot, setEditBot] = useState(null)
  const [guideOpen, setGuideOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try { const r = await getCopilotBots(); setBots(r.data) }
    catch { message.error('載入失敗') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => { setEditBot(null); form.resetFields(); setModalOpen(true) }
  const openEdit = bot => { setEditBot(bot); form.setFieldsValue({ name: bot.name, description: bot.description }); setModalOpen(true) }

  const handleSave = async () => {
    const values = await form.validateFields()
    try {
      if (editBot) { await updateCopilotBot(editBot.id, values); message.success('已更新') }
      else { await createCopilotBot(values); message.success('已建立') }
      setModalOpen(false); load()
    } catch { message.error('儲存失敗') }
  }

  const handleToggle = async (bot, checked) => {
    try { await updateCopilotBot(bot.id, { is_enabled: checked }); load() }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async id => {
    try { await deleteCopilotBot(id); message.success('已刪除'); load() }
    catch { message.error('刪除失敗') }
  }

  const copyUrl = () => {
    navigator.clipboard.writeText(`${BACKEND_URL}/api/copilot/query`)
    message.success('已複製 API URL')
  }

  const columns = [
    { title: '啟用', dataIndex: 'is_enabled', width: 70, render: (v, r) => <Switch checked={v} size="small" onChange={c => handleToggle(r, c)} disabled={!canEdit(user)} /> },
    { title: '機器人名稱', dataIndex: 'name', render: n => <Space><RobotOutlined style={{ color: '#7c3aed' }} /><Text strong>{n}</Text></Space> },
    { title: '說明', dataIndex: 'description', render: d => <Text type="secondary">{d || '-'}</Text> },
    {
      title: 'Query API URL', render: (_, r) => (
        <Space>
          <Text code style={{ fontSize: 12 }}>{BACKEND_URL}/api/copilot/query</Text>
          <Tooltip title="複製"><Button size="small" icon={<CopyOutlined />} onClick={copyUrl} /></Tooltip>
        </Space>
      )
    },
    { title: 'Bot ID', dataIndex: 'id', width: 80, render: id => <Tag color="purple">{id}</Tag> },
    {
      title: '操作', width: 120, render: (_, r) => (
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
        <h2>Copilot 機器人管理</h2>
        <Space>
          <Button icon={<QuestionCircleOutlined />} onClick={() => setGuideOpen(true)}>Copilot Studio 設定教學</Button>
          {canEdit(user) && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增機器人</Button>}
        </Space>
      </div>
      <Text type="secondary" style={{ display: 'block', marginBottom: 16, fontSize: 13 }}>
        在 Copilot Studio 建立機器人後，透過 HTTP 動作呼叫下方 Query API URL，即可使用後台的關鍵字規則與知識庫 AI 回覆。
      </Text>
      <Table rowKey="id" dataSource={bots} columns={columns} loading={loading} pagination={{ pageSize: 10 }} />

      <Modal title={editBot ? '編輯機器人' : '新增 Copilot 機器人'} open={modalOpen}
        onOk={handleSave} onCancel={() => setModalOpen(false)} okText="儲存" cancelText="取消">
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="機器人名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
            <Input placeholder="例：JILI 客服機器人" />
          </Form.Item>
          <Form.Item name="description" label="說明（選填）">
            <Input.TextArea rows={2} placeholder="用途說明" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="Copilot Studio 設定教學" open={guideOpen} onCancel={() => setGuideOpen(false)} footer={null} width={680}>
        <div style={{ lineHeight: 2 }}>
          <Text strong style={{ fontSize: 15 }}>在 Teams 建立 Copilot Studio 群組機器人</Text>
          <br /><br />

          <Text strong>Step 1：建立 Copilot</Text>
          <ol>
            <li>前往 <a href="https://copilotstudio.microsoft.com" target="_blank" rel="noreferrer">copilotstudio.microsoft.com</a>（需組織帳號）</li>
            <li>點擊「建立」→「空白 Copilot」</li>
            <li>輸入名稱（例：JILI Bot），選擇語言「中文（繁體）」</li>
            <li>點擊「建立」</li>
          </ol>

          <Text strong>Step 2：新增 HTTP 動作主題</Text>
          <ol>
            <li>左側選單點「主題」→「新增主題」→「從空白」</li>
            <li>在觸發條件輸入：「當收到訊息時」，觸發詞輸入任意關鍵字（例：你好、請問）</li>
            <li>新增節點「呼叫動作」→「HTTP 要求」</li>
            <li>設定如下：
              <ul>
                <li>方法：<Tag>POST</Tag></li>
                <li>URL：<Text code>{BACKEND_URL}/api/copilot/query</Text></li>
                <li>Content-Type：<Text code>application/json</Text></li>
                <li>本文（Body）：
                  <Paragraph code copyable style={{ fontSize: 12 }}>
                    {`{\n  "bot_id": 你的Bot_ID,\n  "question": "$\{System.Activity.Text\}",\n  "conversation_id": "$\{System.Conversation.Id\}",\n  "conversation_name": "$\{System.Conversation.Name\}"\n}`}
                  </Paragraph>
                </li>
              </ul>
            </li>
            <li>回應變數：儲存為 <Text code>httpResponse</Text></li>
            <li>新增「傳送訊息」節點，內容填：<Text code>{`{httpResponse.answer}`}</Text></li>
          </ol>

          <Text strong>Step 3：發布到 Teams</Text>
          <ol>
            <li>左上角點「發布」</li>
            <li>「頻道」→「Microsoft Teams」→「開啟 Teams」</li>
            <li>在 Teams 搜尋機器人名稱，加入群組即可使用</li>
          </ol>

          <Text type="secondary" style={{ fontSize: 12 }}>
            提示：Bot ID 請參考上方表格的「Bot ID」欄位。每個 Copilot 機器人對應一個 Bot ID，可建立多個針對不同群組。
          </Text>
        </div>
      </Modal>
    </Card>
  )
}
