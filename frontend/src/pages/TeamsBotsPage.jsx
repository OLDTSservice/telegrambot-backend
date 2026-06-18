import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Space,
  Popconfirm, message, Tag, Typography, Card, Steps, Alert, Divider,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  QuestionCircleOutlined, CopyOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import { getTeamsBots, createTeamsBot, updateTeamsBot, deleteTeamsBot } from '../api'

const { Text, Link, Paragraph } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

const BACKEND_URL = 'https://tg-admin-backend-rm99.onrender.com'

const setupSteps = [
  {
    title: '建立 Azure App 註冊',
    content: (
      <div style={{ lineHeight: 2 }}>
        <Paragraph>1. 前往 <Link href="https://portal.azure.com" target="_blank">Azure Portal</Link>，登入 Microsoft 帳號</Paragraph>
        <Paragraph>2. 搜尋「<b>App registrations</b>」→ 點「<b>New registration</b>」</Paragraph>
        <Paragraph>3. 填入名稱（例如：MyTeamsBot），選擇「<b>Accounts in any organizational directory and personal Microsoft accounts</b>（多租戶）」</Paragraph>
        <Paragraph>4. 點「<b>Register</b>」完成</Paragraph>
        <Paragraph>5. 記下「<b>Application (client) ID</b>」，這就是您的 <b>App ID</b></Paragraph>
      </div>
    ),
  },
  {
    title: '取得 App Password（Client Secret）',
    content: (
      <div style={{ lineHeight: 2 }}>
        <Paragraph>1. 在剛建立的 App Registration 頁面，點左側「<b>Certificates &amp; secrets</b>」</Paragraph>
        <Paragraph>2. 點「<b>New client secret</b>」，填入描述，選擇有效期限</Paragraph>
        <Paragraph>3. 點「<b>Add</b>」後，立即複製「<b>Value</b>」欄的值（離開頁面後將無法再查看）</Paragraph>
        <Paragraph>4. 這個值就是您的 <b>App Password</b></Paragraph>
      </div>
    ),
  },
  {
    title: '建立 Azure Bot Service',
    content: (
      <div style={{ lineHeight: 2 }}>
        <Paragraph>1. 在 Azure Portal 搜尋「<b>Azure Bot</b>」→ 點「<b>Create</b>」</Paragraph>
        <Paragraph>2. 填寫機器人名稱，選擇訂閱和資源群組</Paragraph>
        <Paragraph>3. 在「<b>Microsoft App ID</b>」欄位，選擇「<b>Use existing app registration</b>」，填入步驟一的 App ID</Paragraph>
        <Paragraph>4. 點「<b>Review + create</b>」→「<b>Create</b>」完成建立</Paragraph>
      </div>
    ),
  },
  {
    title: '設定 Messaging Endpoint',
    content: (botId) => (
      <div style={{ lineHeight: 2 }}>
        <Paragraph>1. 進入剛建立的 Azure Bot 資源，點左側「<b>Configuration</b>」</Paragraph>
        <Paragraph>2. 在「<b>Messaging endpoint</b>」填入以下網址：</Paragraph>
        <div style={{ background: '#f5f5f5', padding: '8px 12px', borderRadius: 4, marginBottom: 8 }}>
          <Text code style={{ fontSize: 12 }}>
            {BACKEND_URL}/api/teams-bots/webhook/{botId || '<機器人ID>'}
          </Text>
          <Button
            size="small" type="link" icon={<CopyOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(`${BACKEND_URL}/api/teams-bots/webhook/${botId || ''}`)
              message.success('已複製')
            }}
          >複製</Button>
        </div>
        <Paragraph>3. 點「<b>Apply</b>」儲存</Paragraph>
      </div>
    ),
  },
  {
    title: '新增 Teams 頻道',
    content: (
      <div style={{ lineHeight: 2 }}>
        <Paragraph>1. 在 Azure Bot 資源，點左側「<b>Channels</b>」</Paragraph>
        <Paragraph>2. 點「<b>Microsoft Teams</b>」圖示</Paragraph>
        <Paragraph>3. 同意服務條款，點「<b>Apply</b>」</Paragraph>
        <Paragraph>4. 回到 Channels 頁面，點「<b>Open in Teams</b>」即可與機器人對話</Paragraph>
      </div>
    ),
  },
]

function SetupGuide({ botId, onClose }) {
  const [current, setCurrent] = useState(0)

  return (
    <Modal
      title="Teams 機器人建立指引"
      open
      onCancel={onClose}
      footer={
        <Space>
          {current > 0 && <Button onClick={() => setCurrent(c => c - 1)}>上一步</Button>}
          {current < setupSteps.length - 1 && (
            <Button type="primary" onClick={() => setCurrent(c => c + 1)}>下一步</Button>
          )}
          {current === setupSteps.length - 1 && (
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={onClose}>完成</Button>
          )}
        </Space>
      }
      width={640}
    >
      <Steps
        current={current}
        size="small"
        style={{ marginBottom: 24 }}
        items={setupSteps.map(s => ({ title: s.title }))}
      />
      <div style={{ minHeight: 200 }}>
        {typeof setupSteps[current].content === 'function'
          ? setupSteps[current].content(botId)
          : setupSteps[current].content}
      </div>
    </Modal>
  )
}

export default function TeamsBotsPage({ user }) {
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingBot, setEditingBot] = useState(null)
  const [guideBot, setGuideBot] = useState(null)
  const [guideOpen, setGuideOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try { setBots((await getTeamsBots()).data) }
    catch { message.error('載入失敗') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openAdd = () => { setEditingBot(null); form.resetFields(); setModalOpen(true) }
  const openEdit = bot => { setEditingBot(bot); form.setFieldsValue({ name: bot.name, app_id: bot.app_id, app_password: '', tenant_id: bot.tenant_id || '' }); setModalOpen(true) }
  const openGuide = bot => { setGuideBot(bot); setGuideOpen(true) }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    if (!values.app_password && editingBot) delete values.app_password
    try {
      if (editingBot) { await updateTeamsBot(editingBot.id, values); message.success('已更新') }
      else { await createTeamsBot(values); message.success('已新增') }
      setModalOpen(false); load()
    } catch (err) { message.error(err.response?.data?.detail || '操作失敗') }
  }

  const handleToggle = async (bot, checked) => {
    try { await updateTeamsBot(bot.id, { is_enabled: checked }); load() }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async id => {
    try { await deleteTeamsBot(id); message.success('已刪除'); load() }
    catch { message.error('刪除失敗') }
  }

  const columns = [
    {
      title: '啟用', dataIndex: 'is_enabled', width: 80,
      render: (val, record) => (
        <Switch checked={val} onChange={checked => handleToggle(record, checked)} disabled={!canEdit(user)} size="small" />
      ),
    },
    {
      title: '機器人名稱', dataIndex: 'name',
      render: (name, record) => (
        <Space>
          <span style={{ fontSize: 18 }}>🤖</span>
          <Text strong>{name}</Text>
          {record.is_enabled && <Tag color="blue">已啟用</Tag>}
        </Space>
      ),
    },
    {
      title: 'App ID', dataIndex: 'app_id',
      render: id => <Text code style={{ fontSize: 11 }}>{id}</Text>,
    },
    {
      title: 'Webhook 端點', dataIndex: 'id',
      render: id => (
        <Space size={4}>
          <Text code style={{ fontSize: 11 }}>.../webhook/{id}</Text>
          <Button size="small" type="link" icon={<CopyOutlined />}
            onClick={() => { navigator.clipboard.writeText(`${BACKEND_URL}/api/teams-bots/webhook/${id}`); message.success('已複製') }} />
        </Space>
      ),
    },
    {
      title: '操作', width: 140,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<QuestionCircleOutlined />} onClick={() => openGuide(record)}>指引</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} disabled={!canEdit(user)} />
          <Popconfirm title="確定要刪除此機器人？" onConfirm={() => handleDelete(record.id)} disabled={!canEdit(user)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <div className="page-header">
        <h2>Teams 機器人管理</h2>
        <Space>
          <Button icon={<QuestionCircleOutlined />} onClick={() => { setGuideBot(null); setGuideOpen(true) }}>建立指引</Button>
          {canEdit(user) && <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增機器人</Button>}
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Teams 機器人使用 Microsoft Azure Bot Service（Webhook 模式）"
        description="需要先在 Azure 建立 App Registration 和 Bot Service，再將 Webhook 端點填入 Azure Bot Configuration。點「建立指引」查看完整步驟。"
      />

      <Table
        rowKey="id"
        dataSource={bots}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: '尚未新增任何 Teams 機器人' }}
      />

      <Modal
        title={editingBot ? '編輯 Teams 機器人' : '新增 Teams 機器人'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={editingBot ? '儲存' : '新增'}
        cancelText="取消"
        width={520}
      >
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="請先完成 Azure App Registration，再填入以下資訊。點「建立指引」按鈕查看教學。" />
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="name" label="機器人名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
            <Input placeholder="例如：客服機器人" />
          </Form.Item>
          <Form.Item name="app_id" label="App ID（Azure App Registration Client ID）" rules={[{ required: true, message: '請輸入 App ID' }]}>
            <Input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </Form.Item>
          <Form.Item
            name="app_password"
            label="App Password（Client Secret）"
            rules={editingBot ? [] : [{ required: true, message: '請輸入 App Password' }]}
          >
            <Input.Password placeholder={editingBot ? '不修改請留空' : '從 Azure 取得的 Client Secret'} />
          </Form.Item>
          <Form.Item name="tenant_id" label="Tenant ID（選填，留空表示多租戶）">
            <Input placeholder="留空 = 允許所有組織（多租戶）" />
          </Form.Item>
        </Form>
      </Modal>

      {guideOpen && <SetupGuide botId={guideBot?.id} onClose={() => setGuideOpen(false)} />}
    </Card>
  )
}
