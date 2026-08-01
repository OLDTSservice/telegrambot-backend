import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Typography, Alert, Empty,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, StopOutlined, CopyOutlined, KeyOutlined } from '@ant-design/icons'
import { getTelegramIgnores, createTelegramIgnore, updateTelegramIgnore, deleteTelegramIgnore, getBots } from '../api'
import { formatDateTime } from '../utils/datetime'

const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

export default function TelegramIgnorePage({ user }) {
  const [items, setItems] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState(null)
  const [form] = Form.useForm()
  const [copyModalOpen, setCopyModalOpen] = useState(false)
  const [copyingItem, setCopyingItem] = useState(null)
  const [copyTargetBotId, setCopyTargetBotId] = useState(null)
  const [copying, setCopying] = useState(false)
  const [exceptionModalOpen, setExceptionModalOpen] = useState(false)
  const [exceptionItem, setExceptionItem] = useState(null)
  const [exceptionKeyword, setExceptionKeyword] = useState('')
  const [savingException, setSavingException] = useState(false)

  const load = async () => {
    try {
      const bRes = await getBots()
      setBots(bRes.data)
    } catch { message.error('載入失敗') }
  }

  const loadItems = async (botId) => {
    setLoading(true)
    try {
      const iRes = await getTelegramIgnores({ bot_id: botId })
      setItems(iRes.data)
    } catch { message.error('載入忽略名單失敗') }
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
        await updateTelegramIgnore(editingItem.id, values)
        message.success('已更新')
      } else {
        await createTelegramIgnore(values)
        message.success('已新增')
      }
      setModalOpen(false)
      if (selectedBotId) loadItems(selectedBotId)
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggle = async (item, checked) => {
    try { await updateTelegramIgnore(item.id, { is_enabled: checked }); if (selectedBotId) loadItems(selectedBotId) }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async id => {
    try { await deleteTelegramIgnore(id); message.success('已刪除'); if (selectedBotId) loadItems(selectedBotId) }
    catch { message.error('刪除失敗') }
  }

  const openCopy = (item) => {
    setCopyingItem(item)
    setCopyTargetBotId(null)
    setCopyModalOpen(true)
  }

  const handleCopySubmit = async () => {
    if (!copyTargetBotId) {
      message.warning('請選擇要複製到的機器人')
      return
    }
    setCopying(true)
    try {
      await createTelegramIgnore({
        bot_id: copyTargetBotId,
        identifier: copyingItem.identifier,
        note: copyingItem.note || null,
        exception_keyword: copyingItem.exception_keyword || null,
      })
      message.success('已複製到目標機器人')
      setCopyModalOpen(false)
      if (selectedBotId === copyTargetBotId) loadItems(selectedBotId)
    } catch (err) {
      message.error(err.response?.data?.detail || '複製失敗')
    } finally {
      setCopying(false)
    }
  }

  const openExceptionModal = (item) => {
    setExceptionItem(item)
    setExceptionKeyword(item.exception_keyword || '')
    setExceptionModalOpen(true)
  }

  const handleExceptionSave = async () => {
    if (!exceptionItem) return
    setSavingException(true)
    try {
      await updateTelegramIgnore(exceptionItem.id, { exception_keyword: exceptionKeyword.trim() })
      message.success('例外關鍵字已儲存')
      setExceptionModalOpen(false)
      if (selectedBotId) loadItems(selectedBotId)
    } catch {
      message.error('儲存失敗')
    } finally {
      setSavingException(false)
    }
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
      title: '例外關鍵字',
      dataIndex: 'exception_keyword',
      width: 160,
      render: (v, record) => (
        <Space size={6}>
          {v
            ? <Text code style={{ fontSize: 12 }}>{v}</Text>
            : <Text type="secondary" style={{ fontSize: 12 }}>未設定</Text>}
          <Button size="small" icon={<KeyOutlined />}
            onClick={() => openExceptionModal(record)} disabled={!canEdit(user)}
            title="設定例外關鍵字" />
        </Space>
      ),
    },
    {
      title: '操作', width: 140,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />}
            onClick={() => openEdit(record)} disabled={!canEdit(user)} />
          <Button size="small" icon={<CopyOutlined />}
            onClick={() => openCopy(record)} disabled={!canEdit(user)}
            title="複製到其他機器人" />
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
      <div className="page-header" style={{ marginBottom: 16 }}>
        <h2><StopOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />Telegram 忽略名單</h2>
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
              新增忽略帳號
            </Button>
          )}
        </Space>
      </div>

      <Alert
        type="warning" showIcon style={{ marginBottom: 16 }}
        message="在此名單中的帳號，機器人將完全忽略其傳送的訊息（不回覆關鍵字也不觸發 AI）"
        description={
          <span>
            Telegram 識別碼填入 <Text code>@username</Text>（用戶名稱）或
            <Text code> 數字 user_id</Text>（可透過 @userinfobot 查詢）
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
          locale={{ emptyText: '此機器人的忽略名單為空' }}
        />
      )}

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
            <Input placeholder="例如：廣告帳號、已封鎖用戶" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="複製忽略帳號到其他機器人"
        open={copyModalOpen}
        onOk={handleCopySubmit}
        onCancel={() => setCopyModalOpen(false)}
        okText="複製"
        cancelText="取消"
        confirmLoading={copying}
        width={480}
      >
        {copyingItem && (
          <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 16 }}>
              <Text type="secondary">帳號識別碼：</Text>
              <Text code>{copyingItem.identifier}</Text>
            </div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>目標機器人</Text>
              <Select
                style={{ width: '100%', marginTop: 6 }}
                placeholder="選擇要複製到的機器人"
                value={copyTargetBotId}
                onChange={setCopyTargetBotId}
              >
                {bots.filter(b => b.id !== copyingItem.bot_id).map(b => (
                  <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>
                ))}
              </Select>
            </div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              將以相同的帳號識別碼與備註，在目標機器人下新增一筆忽略名單（不影響原名單）。若目標機器人已有相同識別碼，複製會失敗。
            </Text>
          </div>
        )}
      </Modal>

      <Modal
        title={`例外關鍵字 — ${exceptionItem?.identifier || ''}`}
        open={exceptionModalOpen}
        onOk={handleExceptionSave}
        onCancel={() => setExceptionModalOpen(false)}
        okText="儲存"
        cancelText="取消"
        confirmLoading={savingException}
        width={480}
      >
        <div style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
          此帳號的訊息預設會被完全忽略；若訊息內容包含以下任一關鍵字（逗號分隔可填多個），機器人仍會照常處理該則訊息。留空則維持完全忽略。
        </div>
        <Input
          value={exceptionKeyword}
          onChange={e => setExceptionKeyword(e.target.value)}
          placeholder="例如：whitelist, 緊急"
        />
      </Modal>
    </Card>
  )
}
