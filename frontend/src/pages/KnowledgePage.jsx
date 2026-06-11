import React, { useEffect, useState } from 'react'
import {
  Table, Button, Switch, Upload, Select, Modal, Form,
  Popconfirm, message, Space, Card, Typography, Tag, Progress,
} from 'antd'
import {
  UploadOutlined, DeleteOutlined, FileTextOutlined,
  FilePdfOutlined, FileExcelOutlined, FileWordOutlined,
} from '@ant-design/icons'
import { getDocs, uploadDoc, updateDoc, deleteDoc, getBots } from '../api'

const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

const FILE_ICON = {
  pdf: <FilePdfOutlined style={{ color: '#ff4d4f' }} />,
  docx: <FileWordOutlined style={{ color: '#1677ff' }} />,
  doc: <FileWordOutlined style={{ color: '#1677ff' }} />,
  xlsx: <FileExcelOutlined style={{ color: '#52c41a' }} />,
  xls: <FileExcelOutlined style={{ color: '#52c41a' }} />,
}

const formatSize = bytes => {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

export default function KnowledgePage({ user }) {
  const [docs, setDocs] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [pendingFile, setPendingFile] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [dRes, bRes] = await Promise.all([getDocs(), getBots()])
      setDocs(dRes.data)
      setBots(bRes.data)
    } catch {
      message.error('載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const botName = id => bots.find(b => b.id === id)?.name || `Bot #${id}`

  const handleUpload = async () => {
    if (!selectedBotId) { message.warning('請先選擇要綁定的機器人'); return }
    if (!pendingFile) { message.warning('請選擇要上傳的文件'); return }

    const formData = new FormData()
    formData.append('bot_id', selectedBotId)
    formData.append('file', pendingFile)

    setUploading(true)
    setUploadProgress(0)
    try {
      await uploadDoc(formData)
      message.success('文件上傳並處理完成')
      setUploadModalOpen(false)
      setPendingFile(null)
      setSelectedBotId(null)
      load()
    } catch (err) {
      message.error(err.response?.data?.detail || '上傳失敗')
    } finally {
      setUploading(false)
    }
  }

  const handleToggle = async (doc, checked) => {
    try {
      await updateDoc(doc.id, { is_enabled: checked })
      load()
    } catch {
      message.error('切換失敗')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteDoc(id)
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
      title: '文件名稱',
      dataIndex: 'original_filename',
      render: (name, record) => (
        <Space>
          {FILE_ICON[record.file_type] || <FileTextOutlined />}
          <Text>{name}</Text>
        </Space>
      ),
    },
    {
      title: '格式',
      dataIndex: 'file_type',
      width: 80,
      render: t => <Tag>{(t || '').toUpperCase()}</Tag>,
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      width: 100,
      render: formatSize,
    },
    {
      title: '綁定機器人',
      dataIndex: 'bot_id',
      width: 160,
      render: id => botName(id),
    },
    {
      title: '上傳時間',
      dataIndex: 'created_at',
      width: 160,
      render: t => new Date(t).toLocaleString('zh-TW'),
    },
    {
      title: '操作',
      width: 80,
      render: (_, record) => (
        <Popconfirm title="確定刪除此文件？" onConfirm={() => handleDelete(record.id)}
          disabled={!canEdit(user)}>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <Card>
      <div className="page-header">
        <h2>知識庫管理</h2>
        {canEdit(user) && (
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadModalOpen(true)}>
            上傳文件
          </Button>
        )}
      </div>

      <Text type="secondary" style={{ display: 'block', marginBottom: 16, fontSize: 13 }}>
        上傳文件後，機器人將根據文件內容以 AI 回覆相關問題。支援格式：PDF、Word、Excel、TXT、CSV
      </Text>

      <Table
        rowKey="id"
        dataSource={docs}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: '尚未上傳任何知識庫文件' }}
      />

      <Modal
        title="上傳知識庫文件"
        open={uploadModalOpen}
        onOk={handleUpload}
        onCancel={() => { setUploadModalOpen(false); setPendingFile(null); setSelectedBotId(null) }}
        okText="上傳並處理"
        cancelText="取消"
        confirmLoading={uploading}
      >
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <Text strong>綁定機器人</Text>
            <Select
              style={{ width: '100%', marginTop: 6 }}
              placeholder="選擇要綁定的機器人"
              value={selectedBotId}
              onChange={setSelectedBotId}
            >
              {bots.map(b => (
                <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>
              ))}
            </Select>
          </div>

          <div>
            <Text strong>選擇文件</Text>
            <Upload
              beforeUpload={file => { setPendingFile(file); return false }}
              maxCount={1}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.csv"
              onRemove={() => setPendingFile(null)}
              style={{ marginTop: 6 }}
            >
              <Button icon={<UploadOutlined />} style={{ marginTop: 6 }}>選擇文件</Button>
            </Upload>
          </div>

          {uploading && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>正在處理文件並建立向量索引，請稍候…</Text>
              <Progress percent={uploadProgress} status="active" />
            </div>
          )}
        </div>
      </Modal>
    </Card>
  )
}
