import React, { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Space,
  Popconfirm, message, Tag, Typography, Card, Tabs, Select,
  Pagination, Empty, Spin, InputNumber, Tooltip,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, RobotOutlined, SearchOutlined, SafetyOutlined } from '@ant-design/icons'
import { getBots, createBot, updateBot, deleteBot, getRescueSetting, updateRescueSetting, getNotifySetting, updateNotifySetting } from '../api'
import api from '../api'

const { TextArea } = Input

const { Text } = Typography
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

// ── 機器人列表 Tab ──────────────────────────────────────────────────────────
function BotListTab({ user }) {
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

  const openAdd = () => { setEditingBot(null); form.resetFields(); setModalOpen(true) }
  const openEdit = (bot) => { setEditingBot(bot); form.setFieldsValue({ name: bot.name, token: bot.token }); setModalOpen(true) }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingBot) { await updateBot(editingBot.id, values); message.success('已更新') }
      else { await createBot(values); message.success('已新增') }
      setModalOpen(false); load()
    } catch (err) { message.error(err.response?.data?.detail || '操作失敗') }
  }

  const handleToggle = async (bot, checked) => {
    try { await updateBot(bot.id, { is_enabled: checked }); message.success(checked ? '已啟用' : '已停用'); load() }
    catch { message.error('切換失敗') }
  }

  const handleDelete = async (id) => {
    try { await deleteBot(id); message.success('已刪除'); load() }
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
          <RobotOutlined style={{ color: record.is_enabled ? '#52c41a' : '#bbb' }} />
          <Text strong>{name}</Text>
          {record.is_enabled && <Tag color="green" style={{ fontSize: 11 }}>運行中</Tag>}
        </Space>
      ),
    },
    {
      title: 'Token', dataIndex: 'token', ellipsis: true,
      render: token => <Text code style={{ fontSize: 12 }}>{token.slice(0, 20)}…</Text>,
    },
    {
      title: '建立時間', dataIndex: 'created_at', width: 160,
      render: t => new Date(t).toLocaleString('zh-TW'),
    },
    {
      title: '操作', width: 120,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} disabled={!canEdit(user)} />
          <Popconfirm title="確定要刪除此機器人？" onConfirm={() => handleDelete(record.id)} disabled={!canEdit(user)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div className="page-header">
        <h2>Telegram 機器人管理</h2>
        {canEdit(user) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增機器人</Button>
        )}
      </div>
      <Table rowKey="id" dataSource={bots} columns={columns} loading={loading}
        pagination={{ pageSize: 10 }} locale={{ emptyText: '尚未新增任何機器人' }} />
      <Modal title={editingBot ? '編輯機器人' : '新增機器人'} open={modalOpen}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)}
        okText={editingBot ? '儲存' : '新增'} cancelText="取消">
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="機器人名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
            <Input placeholder="例如：客服機器人" />
          </Form.Item>
          <Form.Item name="token" label="Telegram Bot Token" rules={[{ required: true, message: '請輸入 Token' }]}>
            <Input.Password placeholder="從 @BotFather 取得的 Token" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

// ── 群組管理 Tab ────────────────────────────────────────────────────────────
function GroupManageTab({ user }) {
  const [bots, setBots] = useState([])
  const [selectedBotId, setSelectedBotId] = useState(null)
  const [groups, setGroups] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)

  // 廠商驗證 Modal
  const [vendorModal, setVendorModal] = useState(false)
  const [editingGroup, setEditingGroup] = useState(null)
  const [vendorCheck, setVendorCheck] = useState(false)
  const [allowedVendors, setAllowedVendors] = useState('')
  const [vendorSaving, setVendorSaving] = useState(false)

  useEffect(() => { getBots().then(r => setBots(r.data)) }, [])

  const loadGroups = useCallback(async (botId, p = 1, kw = search) => {
    if (!botId) return
    setLoading(true)
    try {
      const params = { bot_id: botId, page: p, page_size: 50 }
      if (kw) params.search = kw
      const res = await api.get('/group-settings', { params })
      setGroups(res.data.items)
      setTotal(res.data.total)
      setPage(p)
    } catch {
      message.error('載入群組失敗')
    } finally {
      setLoading(false)
    }
  }, [search])

  const handleBotChange = (botId) => {
    setSelectedBotId(botId)
    setSearch('')
    setPage(1)
    loadGroups(botId, 1, '')
  }

  const handleSearch = (val) => {
    setSearch(val)
    setPage(1)
    loadGroups(selectedBotId, 1, val)
  }

  const handleToggleAI = async (chatId, enabled) => {
    try {
      await api.put(`/group-settings/${encodeURIComponent(chatId)}`, { bot_id: selectedBotId, ai_enabled: enabled })
      setGroups(prev => prev.map(g => g.chat_id === chatId ? { ...g, ai_enabled: enabled } : g))
    } catch {
      message.error('切換失敗')
    }
  }

  const openVendorModal = (group) => {
    setEditingGroup(group)
    setVendorCheck(group.whitelist_vendor_check || false)
    setAllowedVendors(group.whitelist_allowed_vendors || '')
    setVendorModal(true)
  }

  const handleVendorSave = async () => {
    if (!editingGroup) return
    setVendorSaving(true)
    try {
      await api.put(`/group-settings/${encodeURIComponent(editingGroup.chat_id)}`, {
        bot_id: selectedBotId,
        whitelist_vendor_check: vendorCheck,
        whitelist_allowed_vendors: allowedVendors.trim() || null,
      })
      setGroups(prev => prev.map(g =>
        g.chat_id === editingGroup.chat_id
          ? { ...g, whitelist_vendor_check: vendorCheck, whitelist_allowed_vendors: allowedVendors.trim() || null }
          : g
      ))
      message.success('廠商驗證設定已儲存')
      setVendorModal(false)
    } catch {
      message.error('儲存失敗')
    } finally {
      setVendorSaving(false)
    }
  }

  const chatTypeLabel = (type) => {
    const map = { group: '群組', supergroup: '超級群組', private: '私聊', channel: '頻道' }
    return map[type] || type || '-'
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <Select style={{ width: 220 }} placeholder="選擇機器人" value={selectedBotId} onChange={handleBotChange}>
          {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
        </Select>
        {selectedBotId && (
          <Input.Search
            placeholder="搜尋群組名稱"
            allowClear
            style={{ width: 240 }}
            value={search}
            onChange={e => { if (!e.target.value) { setSearch(''); loadGroups(selectedBotId, 1, '') } else setSearch(e.target.value) }}
            onSearch={handleSearch}
            prefix={<SearchOutlined style={{ color: '#bbb' }} />}
          />
        )}
        {selectedBotId && <span style={{ fontSize: 12, color: '#888' }}>共 {total} 個群組</span>}
      </div>

      {!selectedBotId ? (
        <Empty description="請先選擇機器人" style={{ padding: 48 }} />
      ) : loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : groups.length === 0 ? (
        <Empty description="此機器人尚無群組紀錄" style={{ padding: 48 }} />
      ) : (
        <>
          <Table
            rowKey="chat_id"
            dataSource={groups}
            pagination={false}
            columns={[
              {
                title: 'AI 問答',
                dataIndex: 'ai_enabled',
                width: 90,
                render: (val, record) => (
                  <Switch checked={val} size="small"
                    onChange={checked => handleToggleAI(record.chat_id, checked)}
                    disabled={!canEdit(user)} />
                ),
              },
              {
                title: '群組名稱',
                dataIndex: 'chat_name',
                render: name => <Text strong>{name}</Text>,
              },
              {
                title: '類型', dataIndex: 'chat_type', width: 100,
                render: t => <Tag>{chatTypeLabel(t)}</Tag>,
              },
              {
                title: '最後活躍', dataIndex: 'last_active', width: 120,
                render: d => <Text type="secondary" style={{ fontSize: 12 }}>{d || '-'}</Text>,
              },
              {
                title: '白名單廠商驗證',
                width: 130,
                render: (_, record) => (
                  <Space size={6}>
                    <Tag color={record.whitelist_vendor_check ? 'blue' : 'default'}>
                      {record.whitelist_vendor_check ? '已啟用' : '未啟用'}
                    </Tag>
                    {canEdit(user) && (
                      <Tooltip title="廠商驗證設定">
                        <Button
                          size="small"
                          icon={<SafetyOutlined />}
                          onClick={() => openVendorModal(record)}
                        />
                      </Tooltip>
                    )}
                  </Space>
                ),
              },
            ]}
            locale={{ emptyText: '無符合條件的群組' }}
          />

          <Modal
            title={`廠商驗證設定 — ${editingGroup?.chat_name || ''}`}
            open={vendorModal}
            onOk={handleVendorSave}
            onCancel={() => setVendorModal(false)}
            okText="儲存"
            cancelText="取消"
            confirmLoading={vendorSaving}
            width={500}
          >
            <div style={{ marginBottom: 16, color: '#666', fontSize: 13 }}>
              啟用後，此群組收到的白名單申請只有解析出的廠商名稱符合允許清單時才會執行；不符合則靜默拒絕。
            </div>
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Switch
                  checked={vendorCheck}
                  onChange={setVendorCheck}
                  checkedChildren="啟用" unCheckedChildren="關閉"
                />
                <Text>廠商驗證開關</Text>
              </Space>
            </div>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                允許廠商前綴
                <Text type="secondary" style={{ fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
                  （逗號分隔，不分大小寫，例：TitanTR1_SCFLY, VendorB）
                </Text>
              </div>
              <TextArea
                rows={4}
                value={allowedVendors}
                onChange={e => setAllowedVendors(e.target.value)}
                disabled={!vendorCheck}
                placeholder="TitanTR1_SCFLY, VendorB_Brand"
              />
              <div style={{ marginTop: 6, fontSize: 12, color: '#888' }}>
                填入廠商名稱或前綴；解析出的廠商名稱以任一前綴<strong>開頭</strong>即視為符合。未啟用開關時此欄位不生效。
              </div>
            </div>
          </Modal>
          {total > 50 && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
              <Pagination current={page} pageSize={50} total={total} size="small"
                showTotal={t => `共 ${t} 個`}
                onChange={p => loadGroups(selectedBotId, p)} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── AI 機器人救援 Tab ────────────────────────────────────────────────────────
function RescueTab({ user }) {
  const [bots, setBots] = useState([])
  const [settings, setSettings] = useState({})   // botId → { enabled, timeout_minutes }
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState({})        // botId → bool

  useEffect(() => {
    setLoading(true)
    getBots().then(async r => {
      const botList = r.data
      setBots(botList)
      const entries = await Promise.all(
        botList.map(b => getRescueSetting(b.id).then(res => [b.id, res.data]))
      )
      setSettings(Object.fromEntries(entries))
    }).finally(() => setLoading(false))
  }, [])

  const handleToggle = async (botId, enabled) => {
    const cur = settings[botId] || { enabled: false, timeout_minutes: 5 }
    setSettings(prev => ({ ...prev, [botId]: { ...cur, enabled } }))
    setSaving(prev => ({ ...prev, [botId]: true }))
    try {
      await updateRescueSetting(botId, { enabled, timeout_minutes: cur.timeout_minutes })
    } catch { message.error('儲存失敗') }
    finally { setSaving(prev => ({ ...prev, [botId]: false })) }
  }

  const handleTimeout = async (botId, timeout_minutes) => {
    const cur = settings[botId] || { enabled: false, timeout_minutes: 5 }
    setSettings(prev => ({ ...prev, [botId]: { ...cur, timeout_minutes } }))
    setSaving(prev => ({ ...prev, [botId]: true }))
    try {
      await updateRescueSetting(botId, { enabled: cur.enabled, timeout_minutes })
    } catch { message.error('儲存失敗') }
    finally { setSaving(prev => ({ ...prev, [botId]: false })) }
  }

  const columns = [
    {
      title: '機器人名稱', dataIndex: 'name',
      render: (name, record) => (
        <Space>
          <RobotOutlined style={{ color: record.is_enabled ? '#52c41a' : '#bbb' }} />
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: (
        <Tooltip title="開啟後，若群組 AI 關閉且訊息逾時未被直接引用回覆，AI 將自動接手">
          啟用救援 ⓘ
        </Tooltip>
      ),
      width: 110,
      render: (_, record) => {
        const s = settings[record.id]
        return (
          <Switch
            checked={s?.enabled ?? false}
            loading={saving[record.id]}
            onChange={v => handleToggle(record.id, v)}
            disabled={!canEdit(user)}
          />
        )
      },
    },
    {
      title: (
        <Tooltip title="訊息傳送後超過此分鐘數且無直接引用回覆，才觸發 AI 救援">
          逾時時間（分鐘）ⓘ
        </Tooltip>
      ),
      width: 180,
      render: (_, record) => {
        const s = settings[record.id]
        return (
          <InputNumber
            min={1} max={1440}
            value={s?.timeout_minutes ?? 5}
            disabled={!canEdit(user) || !s?.enabled}
            onBlur={e => {
              const v = parseInt(e.target.value, 10)
              if (v >= 1) handleTimeout(record.id, v)
            }}
            onPressEnter={e => {
              const v = parseInt(e.target.value, 10)
              if (v >= 1) handleTimeout(record.id, v)
            }}
            style={{ width: 100 }}
            addonAfter="分鐘"
          />
        )
      },
    },
    {
      title: '狀態', width: 100,
      render: (_, record) => {
        const s = settings[record.id]
        if (!s?.enabled) return <Tag>未啟用</Tag>
        return <Tag color="blue">監控中（{s.timeout_minutes} 分）</Tag>
      },
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 12, color: '#888', fontSize: 13 }}>
        針對每個機器人設定是否啟用 AI 救援：當群組 AI 問答關閉，且最後一則訊息在指定時間內未被直接引用回覆，AI 將自動判斷是否為問題並接手回覆，回覆後 AI 保持關閉。忽略名單內的帳號不計入判斷範圍。
      </div>
      <Table
        rowKey="id"
        dataSource={bots}
        columns={columns}
        loading={loading}
        pagination={false}
        locale={{ emptyText: '尚未新增任何機器人' }}
      />
    </div>
  )
}

// ── Notify 管理 Tab ─────────────────────────────────────────────────────────
function NotifyTab({ user }) {
  const [bots, setBots] = useState([])
  const [groups, setGroups] = useState([])
  const [botId, setBotId] = useState(null)
  const [chatId, setChatId] = useState(null)
  const [chatName, setChatName] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(false)
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getBots().then(r => setBots(r.data)).catch(() => {})
    getNotifySetting().then(r => {
      const s = r.data
      if (s.bot_id) {
        setBotId(s.bot_id)
        setChatId(s.chat_id)
        setChatName(s.chat_name || '')
        setEnabled(s.enabled)
        loadGroups(s.bot_id)
      }
    }).catch(() => {})
  }, [])

  const loadGroups = async (bid) => {
    if (!bid) return
    setGroupsLoading(true)
    try {
      const r = await api.get('/group-stats/telegram', { params: { period: 'yearly', value: new Date().getFullYear().toString(), bot_id: bid } })
      setGroups(r.data)
    } catch {}
    finally { setGroupsLoading(false) }
  }

  const handleBotChange = (bid) => {
    setBotId(bid)
    setChatId(null)
    setChatName('')
    loadGroups(bid)
  }

  const handleChatChange = (cid) => {
    setChatId(cid)
    const g = groups.find(g => g.chat_id === cid)
    setChatName(g ? g.chat_name : cid)
  }

  const handleSave = async () => {
    if (!botId || !chatId) { message.warning('請選擇機器人和群組'); return }
    setSaving(true)
    try {
      await updateNotifySetting({ bot_id: botId, chat_id: chatId, chat_name: chatName, enabled })
      message.success('設定已儲存')
    } catch { message.error('儲存失敗') }
    finally { setSaving(false) }
  }

  return (
    <div style={{ maxWidth: 620 }}>
      <div style={{ marginBottom: 16, color: '#555', fontSize: 14 }}>
        選擇一個 Telegram 機器人與目標群組，當 Freshdesk 工單建立成功或失敗時，機器人將自動發送通知到該群組。
      </div>
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>通知開關</div>
            <Switch
              checked={enabled}
              onChange={setEnabled}
              checkedChildren="啟用" unCheckedChildren="關閉"
              disabled={!canEdit(user)}
            />
            <Tag style={{ marginLeft: 12 }} color={enabled ? 'green' : 'default'}>
              {enabled ? '通知已啟用' : '通知未啟用'}
            </Tag>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>發送通知的機器人</div>
            <Select
              style={{ width: '100%' }}
              placeholder="選擇機器人"
              value={botId}
              onChange={handleBotChange}
              disabled={!canEdit(user)}
            >
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>通知目標群組</div>
            <Select
              style={{ width: '100%' }}
              placeholder={botId ? '選擇群組' : '請先選擇機器人'}
              value={chatId}
              onChange={handleChatChange}
              loading={groupsLoading}
              disabled={!canEdit(user) || !botId}
              showSearch
              filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
              options={groups.map(g => ({ value: g.chat_id, label: g.chat_name }))}
            />
            {chatId && (
              <div style={{ marginTop: 6, fontSize: 13, color: '#555' }}>
                群組 ID：<Text code>{chatId}</Text>
              </div>
            )}
          </div>
          {canEdit(user) && (
            <Button type="primary" onClick={handleSave} loading={saving}>儲存設定</Button>
          )}
        </Space>
      </Card>

      <Card title="通知訊息格式預覽" size="small">
        <div style={{ fontFamily: 'monospace', fontSize: 13, background: '#f5f7fa', padding: 12, borderRadius: 6, lineHeight: 2 }}>
          <div>群組名稱：{chatName || '（目標群組名稱）'}</div>
          <div style={{ color: '#52c41a' }}>建立狀態：✅ 成功</div>
          <div>工單編號：#12345</div>
          <hr style={{ border: 'none', borderTop: '1px dashed #ccc', margin: '8px 0' }} />
          <div>群組名稱：{chatName || '（目標群組名稱）'}</div>
          <div style={{ color: '#f5222d' }}>建立狀態：❌ 失敗</div>
          <div>失敗原因：HTTP 500: Internal Server Error</div>
        </div>
      </Card>
    </div>
  )
}

// ── 主頁面 ──────────────────────────────────────────────────────────────────
export default function BotsPage({ user }) {
  return (
    <Card>
      <Tabs
        defaultActiveKey="bots"
        items={[
          {
            key: 'bots',
            label: <span><RobotOutlined /> 機器人管理</span>,
            children: <BotListTab user={user} />,
          },
          {
            key: 'groups',
            label: '群組管理',
            children: <GroupManageTab user={user} />,
          },
          {
            key: 'rescue',
            label: 'AI機器人救援',
            children: <RescueTab user={user} />,
          },
          {
            key: 'notify',
            label: 'Notify管理',
            children: <NotifyTab user={user} />,
          },
        ]}
      />
    </Card>
  )
}
