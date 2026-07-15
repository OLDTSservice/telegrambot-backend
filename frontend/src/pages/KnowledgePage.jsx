import React, { useEffect, useState, useCallback } from 'react'
import {
  Button, Switch, Upload, Select, Modal, Form, Input,
  Popconfirm, message, Space, Tag, Spin, Pagination, Tabs, Empty,
} from 'antd'
import {
  UploadOutlined, DeleteOutlined, FileTextOutlined, EditOutlined,
  FilePdfOutlined, FileExcelOutlined, FileWordOutlined,
  DownloadOutlined, PlusOutlined, BookOutlined, MessageOutlined, SearchOutlined,
} from '@ant-design/icons'
import api, { getDocs, uploadDoc, updateDoc, deleteDoc, getBots } from '../api'

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

// ── Q&A 編輯 Modal ─────────────────────────────────────────────────────────
function QAModal({ open, onClose, onSave, initial, docs }) {
  const [form] = Form.useForm()
  useEffect(() => {
    if (open) form.setFieldsValue(initial || { question: '', keywords: '', answer: '', doc_id: undefined })
  }, [open, initial])

  const handleOk = async () => {
    try {
      const vals = await form.validateFields()
      onSave(vals)
    } catch {}
  }

  return (
    <Modal
      title={initial?.id ? '編輯 Q&A' : '手動新增 Q&A'}
      open={open} onOk={handleOk} onCancel={onClose}
      okText="儲存" cancelText="取消" width={600}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        {!initial?.id && (
          <Form.Item name="doc_id" label="歸屬文件" rules={[{ required: true, message: '請選擇文件' }]}>
            <Select placeholder="選擇要新增到哪一份文件">
              {docs.map(d => <Select.Option key={d.id} value={d.id}>{d.original_filename}</Select.Option>)}
            </Select>
          </Form.Item>
        )}
        <Form.Item name="question" label="問題（Q）" rules={[{ required: true, message: '請輸入問題' }]}>
          <Input.TextArea rows={2} placeholder="問題標題" />
        </Form.Item>
        <Form.Item name="keywords" label="其他說法 / 關鍵字（選填）">
          <Input.TextArea rows={2} placeholder="問題的其他說法或關鍵字，換行分隔" />
        </Form.Item>
        <Form.Item name="answer" label="回答（A）" rules={[{ required: true, message: '請輸入回答' }]}>
          <Input.TextArea rows={4} placeholder="回答內容" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

// ── 知識庫來源 Tab ─────────────────────────────────────────────────────────
function SourceTab({ user }) {
  const [docs, setDocs] = useState([])
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [qas, setQas] = useState([])
  const [qasLoading, setQasLoading] = useState(false)
  const [qasTotal, setQasTotal] = useState(0)
  const [qasPage, setQasPage] = useState(1)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [pendingFile, setPendingFile] = useState(null)
  const [qaModalOpen, setQaModalOpen] = useState(false)
  const [editingQA, setEditingQA] = useState(null)
  const [rebotModal, setRebotModal] = useState({ open: false, doc: null })
  const [rebotBotId, setRebotBotId] = useState(null)
  const [qaSearch, setQaSearch] = useState('')

  const loadDocs = useCallback(async () => {
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
  }, [])

  useEffect(() => { loadDocs() }, [loadDocs])

  const loadQAs = useCallback(async (docId, page = 1) => {
    setQasLoading(true)
    try {
      const [qaRes, countRes] = await Promise.all([
        api.get(`/knowledge/${docId}/qas`, { params: { page, page_size: 50 } }),
        api.get(`/knowledge/${docId}/qas/count`),
      ])
      setQas(qaRes.data)
      setQasTotal(countRes.data.total)
      setQasPage(page)
    } catch {
      message.error('載入 Q&A 失敗')
    } finally {
      setQasLoading(false)
    }
  }, [])

  const handleSelectDoc = (doc) => {
    setSelectedDoc(doc)
    setQaSearch('')
    loadQAs(doc.id, 1)
  }

  const handleUpload = async () => {
    if (!selectedBotId) { message.warning('請先選擇要綁定的機器人'); return }
    if (!pendingFile) { message.warning('請選擇要上傳的文件'); return }
    const formData = new FormData()
    formData.append('bot_id', selectedBotId)
    formData.append('file', pendingFile)
    setUploading(true)
    try {
      await uploadDoc(formData)
      message.success('文件上傳並處理完成')
      setUploadOpen(false)
      setPendingFile(null)
      setSelectedBotId(null)
      loadDocs()
    } catch (err) {
      message.error(err.response?.data?.detail || '上傳失敗')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteDoc(id)
      message.success('已刪除')
      if (selectedDoc?.id === id) { setSelectedDoc(null); setQas([]) }
      loadDocs()
    } catch {
      message.error('刪除失敗')
    }
  }

  const handleDownload = async (doc) => {
    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`/api/knowledge/${doc.id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) { message.error('下載失敗'); return }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = doc.original_filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('下載失敗')
    }
  }

  const handleToggle = async (doc, checked) => {
    try {
      await updateDoc(doc.id, { is_enabled: checked })
      loadDocs()
    } catch {
      message.error('切換失敗')
    }
  }

  const handleSaveQA = async (vals) => {
    try {
      if (editingQA?.id) {
        await api.put(`/knowledge/qas/${editingQA.id}`, vals)
        message.success('已更新')
      } else {
        await api.post('/knowledge/qas', vals)
        message.success('已新增')
      }
      setQaModalOpen(false)
      setEditingQA(null)
      loadDocs()
      if (selectedDoc) loadQAs(vals.doc_id || selectedDoc.id, qasPage)
    } catch (err) {
      message.error(err.response?.data?.detail || '儲存失敗')
    }
  }

  const handleDeleteQA = async (qaId) => {
    try {
      await api.delete(`/knowledge/qas/${qaId}`)
      message.success('已刪除')
      loadDocs()
      if (selectedDoc) loadQAs(selectedDoc.id, qasPage)
    } catch {
      message.error('刪除失敗')
    }
  }

  const botName = id => bots.find(b => b.id === id)?.name || `Bot #${id}`

  const handleRebot = async () => {
    if (!rebotBotId) { message.warning('請選擇機器人'); return }
    try {
      await updateDoc(rebotModal.doc.id, { bot_id: rebotBotId })
      message.success('已更新綁定機器人')
      setRebotModal({ open: false, doc: null })
      setRebotBotId(null)
      loadDocs()
    } catch {
      message.error('更新失敗')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 12 }}>
        {canEdit(user) && (
          <>
            <Button icon={<PlusOutlined />} onClick={() => { setEditingQA(null); setQaModalOpen(true) }}>
              手動新增 Q&A
            </Button>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
              上傳文件
            </Button>
          </>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16 }}>
        {/* 左側文件列表 */}
        <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}>
          <div style={{ padding: '10px 14px', borderBottom: '1px solid #f0f0f0', background: '#fafafa', fontWeight: 500, fontSize: 13 }}>
            文件清單 <Tag style={{ marginLeft: 6 }}>{docs.length} 份</Tag>
          </div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
          ) : docs.length === 0 ? (
            <Empty description="尚未上傳文件" style={{ padding: 24 }} />
          ) : (
            docs.map(doc => (
              <div
                key={doc.id}
                onClick={() => handleSelectDoc(doc)}
                style={{
                  padding: '12px 14px',
                  borderBottom: '1px solid #f5f5f5',
                  cursor: 'pointer',
                  background: selectedDoc?.id === doc.id ? '#e6f4ff' : 'white',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500, fontSize: 13, marginBottom: 6 }}>
                  {FILE_ICON[doc.file_type] || <FileTextOutlined />}
                  <span style={{ wordBreak: 'break-all' }}>{doc.original_filename}</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', fontSize: 12, color: '#888' }}>
                  <span>{botName(doc.bot_id)}</span>
                  <span>·</span>
                  <span>{formatSize(doc.file_size)}</span>
                  <span>·</span>
                  <span>{new Date(doc.created_at).toLocaleDateString('zh-TW')}</span>
                  <Tag color="blue" style={{ marginLeft: 2, fontSize: 11 }}>QA: {doc.qa_count ?? 0}</Tag>
                </div>
                <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
                  <Switch checked={doc.is_enabled} size="small"
                    onChange={(checked, e) => { e.stopPropagation(); handleToggle(doc, checked) }}
                    disabled={!canEdit(user)} />
                  <Button size="small" icon={<DownloadOutlined />} type="link" style={{ padding: 0, height: 'auto' }}
                    onClick={e => { e.stopPropagation(); handleDownload(doc) }}>下載</Button>
                  {canEdit(user) && (
                    <>
                      <Button size="small" icon={<EditOutlined />} type="link" style={{ padding: 0, height: 'auto' }}
                        onClick={e => { e.stopPropagation(); setRebotModal({ open: true, doc }); setRebotBotId(doc.bot_id) }}>
                        換機器人
                      </Button>
                      <Popconfirm title="確定刪除此文件？"
                        onConfirm={e => { e.stopPropagation(); handleDelete(doc.id) }}
                        onClick={e => e.stopPropagation()}>
                        <Button size="small" danger icon={<DeleteOutlined />} type="link" style={{ padding: 0, height: 'auto' }}>刪除</Button>
                      </Popconfirm>
                    </>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* 右側 Q&A 列表 */}
        <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}>
          {!selectedDoc ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, color: '#aaa', gap: 8 }}>
              <BookOutlined style={{ fontSize: 32 }} />
              <span style={{ fontSize: 13 }}>點擊左側文件查看 Q&A 內容</span>
            </div>
          ) : (
            <>
              <div style={{ padding: '10px 14px', borderBottom: '1px solid #f0f0f0', background: '#fafafa', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 500, fontSize: 13, flexShrink: 0 }}>{selectedDoc.original_filename}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Input
                    size="small"
                    placeholder="搜尋關鍵字…"
                    prefix={<SearchOutlined style={{ color: '#bbb' }} />}
                    allowClear
                    style={{ width: 180 }}
                    value={qaSearch}
                    onChange={e => setQaSearch(e.target.value)}
                  />
                  <Tag style={{ flexShrink: 0 }}>
                    {qaSearch
                      ? `${qas.filter(qa => [qa.question, qa.keywords, qa.answer].join(' ').toLowerCase().includes(qaSearch.toLowerCase())).length} / ${qasTotal} 筆`
                      : `共 ${qasTotal} 筆 Q&A`}
                  </Tag>
                </div>
              </div>
              {qasLoading ? (
                <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
              ) : qas.length === 0 ? (
                <Empty description="此文件尚無 Q&A 資料（非 Q&A 格式文件）" style={{ padding: 32 }} />
              ) : (
                <>
                  <div style={{ padding: '8px 0', maxHeight: 520, overflowY: 'auto' }}>
                    {(qaSearch
                      ? qas.filter(qa => [qa.question, qa.keywords, qa.answer].join(' ').toLowerCase().includes(qaSearch.toLowerCase()))
                      : qas
                    ).map((qa, idx) => (
                      <div key={qa.id} style={{ margin: '8px 14px', border: '1px solid #f0f0f0', borderRadius: 6, padding: 12, background: '#fafafa' }}>
                        <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>Q{qasPage > 1 ? (qasPage - 1) * 50 + idx + 1 : idx + 1}</div>
                        <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 2 }}>{qa.question}</div>
                        {qa.keywords && <div style={{ fontSize: 12, color: '#555', marginBottom: 6, whiteSpace: 'pre-wrap' }}>{qa.keywords}</div>}
                        <div style={{ height: 1, background: '#f0f0f0', margin: '6px 0' }} />
                        <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>A{qasPage > 1 ? (qasPage - 1) * 50 + idx + 1 : idx + 1}</div>
                        <div style={{ fontSize: 13, color: '#333', whiteSpace: 'pre-wrap' }}>{qa.answer}</div>
                        {canEdit(user) && (
                          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginTop: 8 }}>
                            <Button size="small" icon={<EditOutlined />}
                              onClick={() => { setEditingQA({ ...qa, doc_id: selectedDoc.id }); setQaModalOpen(true) }}>
                              編輯
                            </Button>
                            <Popconfirm title="確定刪除此 Q&A？" onConfirm={() => handleDeleteQA(qa.id)}>
                              <Button size="small" danger icon={<DeleteOutlined />} />
                            </Popconfirm>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <div style={{ padding: '8px 14px', borderTop: '1px solid #f0f0f0', display: 'flex', justifyContent: 'flex-end' }}>
                    <Pagination
                      current={qasPage} pageSize={50} total={qasTotal} size="small"
                      showTotal={t => `共 ${t} 筆`}
                      onChange={page => loadQAs(selectedDoc.id, page)}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* 上傳 Modal */}
      <Modal title="上傳知識庫文件" open={uploadOpen} onOk={handleUpload} onCancel={() => { setUploadOpen(false); setPendingFile(null); setSelectedBotId(null) }}
        okText="上傳並處理" cancelText="取消" confirmLoading={uploading}>
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>綁定機器人</div>
            <Select style={{ width: '100%' }} placeholder="選擇機器人" value={selectedBotId} onChange={setSelectedBotId}>
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </div>
          <div>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>選擇文件</div>
            <Upload beforeUpload={file => { setPendingFile(file); return false }} maxCount={1}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.csv,.md" onRemove={() => setPendingFile(null)}>
              <Button icon={<UploadOutlined />}>選擇文件</Button>
            </Upload>
          </div>
          {uploading && <div style={{ fontSize: 12, color: '#888' }}>正在處理文件，請稍候…</div>}
        </div>
      </Modal>

      {/* 換機器人 Modal */}
      <Modal title="重新配置機器人" open={rebotModal.open}
        onOk={handleRebot}
        onCancel={() => { setRebotModal({ open: false, doc: null }); setRebotBotId(null) }}
        okText="儲存" cancelText="取消">
        <div style={{ marginTop: 12 }}>
          <div style={{ marginBottom: 8, fontSize: 13, color: '#555' }}>
            文件：<strong>{rebotModal.doc?.original_filename}</strong>
          </div>
          <Select style={{ width: '100%' }} placeholder="選擇機器人" value={rebotBotId} onChange={setRebotBotId}>
            {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
          </Select>
        </div>
      </Modal>

      {/* Q&A 新增/編輯 Modal */}
      <QAModal open={qaModalOpen} onClose={() => { setQaModalOpen(false); setEditingQA(null) }}
        onSave={handleSaveQA} initial={editingQA} docs={docs} />
    </div>
  )
}

// ── 對話日誌 Tab ───────────────────────────────────────────────────────────
function LogsTab({ user }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [docs, setDocs] = useState([])
  const [addToKbModal, setAddToKbModal] = useState({ open: false, log: null })
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [botFilter, setBotFilter] = useState(undefined)
  const [bots, setBots] = useState([])

  const loadLogs = useCallback(async (p = 1, botId = botFilter) => {
    setLoading(true)
    try {
      const params = { page: p, page_size: 20 }
      if (botId) params.bot_id = botId
      const [logsRes, countRes] = await Promise.all([
        api.get('/conversation-logs', { params }),
        api.get('/conversation-logs/count', { params: botId ? { bot_id: botId } : {} }),
      ])
      setLogs(logsRes.data)
      setTotal(countRes.data.total)
      setPage(p)
    } catch {
      message.error('載入失敗')
    } finally {
      setLoading(false)
    }
  }, [botFilter])

  useEffect(() => {
    Promise.all([api.get('/knowledge'), api.get('/bots')]).then(([dRes, bRes]) => {
      setDocs(dRes.data)
      setBots(bRes.data)
    })
    loadLogs(1, undefined)
  }, [])

  const [addToKbForm] = Form.useForm()

  const openAddToKb = (log) => {
    setAddToKbModal({ open: true, log })
    setSelectedDocId(null)
    addToKbForm.setFieldsValue({ question: log.question, answer: log.answer })
  }

  const handleAddToKb = async () => {
    if (!selectedDocId) { message.warning('請選擇文件'); return }
    try {
      const vals = await addToKbForm.validateFields()
      await api.post(`/conversation-logs/${addToKbModal.log.id}/to-knowledge`, {
        doc_id: selectedDocId,
        question: vals.question,
        answer: vals.answer,
      })
      message.success('已新增至知識庫')
      setAddToKbModal({ open: false, log: null })
      setSelectedDocId(null)
    } catch (err) {
      message.error(err.response?.data?.detail || '新增失敗')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <Select allowClear placeholder="篩選機器人" style={{ width: 180 }}
          value={botFilter} onChange={v => { setBotFilter(v); loadLogs(1, v) }}>
          {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
        </Select>
        <span style={{ fontSize: 12, color: '#888' }}>顯示近 7 日紀錄，最多 20 筆/頁</span>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : logs.length === 0 ? (
        <Empty description="近 7 日無對話紀錄" style={{ padding: 40 }} />
      ) : (
        <>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}>
            {logs.map(log => (
              <div key={log.id} style={{ padding: '14px 16px', borderBottom: '1px solid #f5f5f5' }}>
                <div style={{ display: 'flex', gap: 12, marginBottom: 8, fontSize: 12, color: '#999' }}>
                  <span>{new Date(log.created_at).toLocaleString('zh-TW')}</span>
                  <span style={{ color: '#1677ff' }}>{log.chat_name}</span>
                </div>
                <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>Q：{log.question}</div>
                <div style={{ fontSize: 13, color: '#555', lineHeight: 1.6 }}>A：{log.answer}</div>
                {canEdit(user) && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                    <Button size="small" icon={<PlusOutlined />} onClick={() => openAddToKb(log)}>
                      新增至知識庫
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
            <Pagination current={page} pageSize={20} total={total} size="small"
              showTotal={t => `共 ${t} 筆`} onChange={p => loadLogs(p)} />
          </div>
        </>
      )}

      <Modal title="新增至知識庫" open={addToKbModal.open} width={560}
        onOk={handleAddToKb} onCancel={() => { setAddToKbModal({ open: false, log: null }); setSelectedDocId(null) }}
        okText="確認新增" cancelText="取消">
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>歸屬文件</div>
            <Select style={{ width: '100%' }} placeholder="選擇文件"
              value={selectedDocId} onChange={setSelectedDocId}>
              {docs.map(d => <Select.Option key={d.id} value={d.id}>{d.original_filename}</Select.Option>)}
            </Select>
          </div>
          <Form form={addToKbForm} layout="vertical">
            <Form.Item name="question" label="問題（Q）" rules={[{ required: true, message: '請輸入問題' }]}>
              <Input.TextArea rows={2} />
            </Form.Item>
            <Form.Item name="answer" label="回答（A）" rules={[{ required: true, message: '請輸入回答' }]} style={{ marginBottom: 0 }}>
              <Input.TextArea rows={4} />
            </Form.Item>
          </Form>
        </div>
      </Modal>
    </div>
  )
}

// ── AI無解答對話紀錄 Tab ───────────────────────────────────────────────────
function NoAnswerTab({ user }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [docs, setDocs] = useState([])
  const [bots, setBots] = useState([])
  const [botFilter, setBotFilter] = useState(undefined)
  const [addModal, setAddModal] = useState({ open: false, log: null })
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [addForm] = Form.useForm()

  const loadLogs = useCallback(async (p = 1, botId = botFilter) => {
    setLoading(true)
    try {
      const params = { page: p, page_size: 20 }
      if (botId) params.bot_id = botId
      const [logsRes, countRes] = await Promise.all([
        api.get('/no-answer-logs', { params }),
        api.get('/no-answer-logs/count', { params: botId ? { bot_id: botId } : {} }),
      ])
      setLogs(logsRes.data)
      setTotal(countRes.data.total)
      setPage(p)
    } catch {
      message.error('載入失敗')
    } finally {
      setLoading(false)
    }
  }, [botFilter])

  useEffect(() => {
    Promise.all([api.get('/knowledge'), api.get('/bots')]).then(([dRes, bRes]) => {
      setDocs(dRes.data)
      setBots(bRes.data)
    })
    loadLogs(1, undefined)
  }, [])

  const openAdd = (log) => {
    setAddModal({ open: true, log })
    setSelectedDocId(null)
    addForm.setFieldsValue({ question: log.question, answer: '' })
  }

  const handleAddToKb = async () => {
    if (!selectedDocId) { message.warning('請選擇文件'); return }
    try {
      const vals = await addForm.validateFields()
      await api.post(`/no-answer-logs/${addModal.log.id}/to-knowledge`, {
        doc_id: selectedDocId,
        question: vals.question,
        answer: vals.answer,
      })
      message.success('已新增至知識庫')
      setAddModal({ open: false, log: null })
      setSelectedDocId(null)
    } catch (err) {
      message.error(err.response?.data?.detail || '新增失敗')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <Select allowClear placeholder="篩選機器人" style={{ width: 180 }}
          value={botFilter} onChange={v => { setBotFilter(v); loadLogs(1, v) }}>
          {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
        </Select>
        <span style={{ fontSize: 12, color: '#888' }}>顯示近 7 日無解答紀錄，最多 20 筆/頁</span>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : logs.length === 0 ? (
        <Empty description="近 7 日無無解答對話紀錄" style={{ padding: 40 }} />
      ) : (
        <>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}>
            {logs.map(log => (
              <div key={log.id} style={{ padding: '14px 16px', borderBottom: '1px solid #f5f5f5' }}>
                <div style={{ display: 'flex', gap: 12, marginBottom: 8, fontSize: 12, color: '#999' }}>
                  <span>{new Date(log.created_at).toLocaleString('zh-TW')}</span>
                  <span style={{ color: '#1677ff' }}>{log.chat_name}</span>
                </div>
                <div style={{ fontSize: 13, color: '#333', whiteSpace: 'pre-wrap' }}>{log.question}</div>
                {canEdit(user) && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                    <Button size="small" icon={<PlusOutlined />} onClick={() => openAdd(log)}>
                      新增至知識庫
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
            <Pagination current={page} pageSize={20} total={total} size="small"
              showTotal={t => `共 ${t} 筆`} onChange={p => loadLogs(p)} />
          </div>
        </>
      )}

      <Modal title="新增至知識庫" open={addModal.open} width={560}
        onOk={handleAddToKb} onCancel={() => { setAddModal({ open: false, log: null }); setSelectedDocId(null) }}
        okText="確認新增" cancelText="取消">
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>歸屬文件</div>
            <Select style={{ width: '100%' }} placeholder="選擇文件"
              value={selectedDocId} onChange={setSelectedDocId}>
              {docs.map(d => <Select.Option key={d.id} value={d.id}>{d.original_filename}</Select.Option>)}
            </Select>
          </div>
          <Form form={addForm} layout="vertical">
            <Form.Item name="question" label="問題（Q）" rules={[{ required: true, message: '請輸入問題' }]}>
              <Input.TextArea rows={2} />
            </Form.Item>
            <Form.Item name="answer" label="回答（A）" rules={[{ required: true, message: '請輸入回答' }]} style={{ marginBottom: 0 }}>
              <Input.TextArea rows={4} placeholder="請填寫此問題的正確回答" />
            </Form.Item>
          </Form>
        </div>
      </Modal>
    </div>
  )
}

// ── 主頁面 ─────────────────────────────────────────────────────────────────
export default function KnowledgePage({ user }) {
  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 16 }}>知識庫管理</h2>
      <Tabs
        defaultActiveKey="source"
        items={[
          {
            key: 'source',
            label: <span><BookOutlined /> 知識庫來源</span>,
            children: <SourceTab user={user} />,
          },
          {
            key: 'logs',
            label: <span><MessageOutlined /> AI對話日誌</span>,
            children: <LogsTab user={user} />,
          },
          {
            key: 'no-answer',
            label: <span><MessageOutlined /> AI無解答對話紀錄</span>,
            children: <NoAnswerTab user={user} />,
          },
        ]}
      />
    </div>
  )
}
