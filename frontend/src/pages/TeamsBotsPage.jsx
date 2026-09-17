import React, { useEffect, useRef, useState } from 'react'
import {
  Table, Button, Switch, Modal, Form, Input, Space, Select, Tabs, Tooltip,
  Popconfirm, message, Tag, Typography, Card, Alert, Spin, Empty,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, LoginOutlined,
  CopyOutlined, CheckCircleOutlined, SafetyOutlined, IdcardOutlined, SearchOutlined,
} from '@ant-design/icons'
import {
  getTeamsBots, updateTeamsBot, deleteTeamsBot, restartTeamsBot,
  teamsLoginStart, teamsLoginStatus, getTeamsGroups, updateTeamsGroup,
} from '../api'
import { formatDateTime } from '../utils/datetime'

const { Text, Link } = Typography
const { TextArea } = Input
const canEdit = user => user?.role === 'superadmin' || user?.role === 'editor'

// ── 裝置代碼登入 Modal ────────────────────────────────────────────────────────
// 流程：輸入名稱 → 後端向微軟要一組代碼 → 使用者用瀏覽器登入 Teams 個人帳號 → 前端每 5 秒問後端
// 登入是否完成 → 完成後後端已建好機器人並啟動輪詢。重新登入既有機器人時 bot 不為 null。
function LoginModal({ bot, onClose, onDone }) {
  const [form] = Form.useForm()
  const [step, setStep] = useState('name')      // name → code → done/error
  const [session, setSession] = useState(null)
  const [error, setError] = useState(null)
  const timer = useRef(null)
  const finished = useRef(false)   // 成功/失敗後，還在路上的輪詢回應一律忽略，避免蓋掉結果

  useEffect(() => () => clearInterval(timer.current), [])

  const finish = (nextStep, err) => {
    if (finished.current) return false
    finished.current = true
    clearInterval(timer.current)
    if (err) setError(err)
    setStep(nextStep)
    return true
  }

  const start = async () => {
    let name = null
    if (!bot) {
      const v = await form.validateFields()
      name = v.name
    }
    try {
      const r = await teamsLoginStart(name, bot?.id)
      setSession(r.data)
      setStep('code')
      window.open(r.data.verification_uri, '_blank')
      timer.current = setInterval(async () => {
        try {
          const s = await teamsLoginStatus(r.data.session_id)
          if (s.data.status === 'success') {
            if (finish('done')) onDone(s.data.bot)
          } else if (s.data.status === 'error') {
            finish('error', s.data.error || '登入失敗')
          }
        } catch (e) {
          finish('error', e.response?.data?.detail || '查詢登入狀態失敗')
        }
      }, 5000)
    } catch (e) {
      message.error(e.response?.data?.detail || '無法開始登入')
    }
  }

  return (
    <Modal
      title={bot ? `重新登入 — ${bot.name}` : '新增 Teams 機器人（個人帳號登入）'}
      open
      onCancel={onClose}
      footer={
        step === 'name'
          ? [<Button key="c" onClick={onClose}>取消</Button>,
             <Button key="s" type="primary" icon={<LoginOutlined />} onClick={start}>開始登入</Button>]
          : step === 'code'
            ? [<Button key="c" onClick={onClose}>取消</Button>]
            : [<Button key="c" type="primary" onClick={onClose}>關閉</Button>]
      }
      width={520}
    >
      {step === 'name' && (
        <>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="機器人 = 一個 Teams 個人帳號"
            description="按「開始登入」後會顯示一組代碼，請用瀏覽器登入「要當機器人的那個 Teams 個人帳號」。登入只需一次，之後系統會自動續期。該帳號必須先被加進要監看的群組。" />
          {!bot && (
            <Form form={form} layout="vertical">
              <Form.Item name="name" label="機器人名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
                <Input placeholder="例如：Teams 白名單機器人" />
              </Form.Item>
            </Form>
          )}
        </>
      )}
      {step === 'code' && session && (
        <div style={{ textAlign: 'center', padding: '8px 0' }}>
          <div style={{ marginBottom: 8 }}>1. 用瀏覽器開啟</div>
          <Link href={session.verification_uri} target="_blank" style={{ fontSize: 16 }}>{session.verification_uri}</Link>
          <div style={{ margin: '16px 0 8px' }}>2. 輸入代碼</div>
          <Space>
            <Text code copyable={{ text: session.user_code }} style={{ fontSize: 28, letterSpacing: 4, padding: '4px 12px' }}>
              {session.user_code}
            </Text>
          </Space>
          <div style={{ marginTop: 16, color: '#666' }}>3. 用 Teams 個人帳號登入後，這裡會自動完成</div>
          <div style={{ marginTop: 16 }}><Spin /> <Text type="secondary">等待登入中…（代碼 15 分鐘內有效）</Text></div>
        </div>
      )}
      {step === 'done' && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <CheckCircleOutlined style={{ fontSize: 40, color: '#52c41a' }} />
          <div style={{ marginTop: 12, fontSize: 16 }}>登入成功，輪詢已啟動</div>
        </div>
      )}
      {step === 'error' && <Alert type="error" showIcon message={error} />}
    </Modal>
  )
}

// ── 機器人列表 Tab ────────────────────────────────────────────────────────────
function BotsTab({ user }) {
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(false)
  const [loginBot, setLoginBot] = useState(undefined)   // undefined=關閉, null=新增, obj=重新登入
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try { setBots((await getTeamsBots()).data) }
    catch { message.error('載入失敗') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const update = async (bot, patch, okMsg) => {
    try { await updateTeamsBot(bot.id, patch); if (okMsg) message.success(okMsg); load() }
    catch (e) { message.error(e.response?.data?.detail || '更新失敗') }
  }

  const handleEditSave = async () => {
    const v = await form.validateFields()
    await update(editing, v, '已儲存')
    setEditing(null)
  }

  const handleDelete = async id => {
    try { await deleteTeamsBot(id); message.success('已刪除'); load() }
    catch { message.error('刪除失敗') }
  }

  const handleRestart = async bot => {
    try { await restartTeamsBot(bot.id); message.success('已重新啟動'); load() }
    catch (e) { message.error(e.response?.data?.detail || '重啟失敗') }
  }

  const statusTag = bot => {
    if (!bot.logged_in) return <Tag>尚未登入</Tag>
    if (!bot.is_enabled) return <Tag>已停用</Tag>
    if (bot.last_error) return <Tooltip title={bot.last_error}><Tag color="red">異常</Tag></Tooltip>
    if (bot.running) return <Tag color="green">輪詢中</Tag>
    return <Tag color="orange">未運行</Tag>
  }

  const columns = [
    {
      title: '啟用', dataIndex: 'is_enabled', width: 70,
      render: (val, r) => (
        <Switch checked={val} size="small" disabled={!canEdit(user) || !r.logged_in}
          onChange={c => update(r, { is_enabled: c }, c ? '已啟用' : '已停用')} />
      ),
    },
    {
      title: '機器人名稱', dataIndex: 'name',
      render: (name, r) => (
        <Space>
          <span style={{ fontSize: 18 }}>🤖</span>
          <Text strong>{name}</Text>
          {statusTag(r)}
        </Space>
      ),
    },
    {
      title: 'Teams 帳號',
      render: (_, r) => r.logged_in ? (
        <div>
          <div>{r.account_name || '-'}</div>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.account_email || r.account_mri || ''}</Text>
        </div>
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '最後輪詢', dataIndex: 'last_poll_at', width: 150,
      render: v => <Text type="secondary" style={{ fontSize: 12 }}>{v ? formatDateTime(v) : '-'}</Text>,
    },
    {
      title: '白名單處理', dataIndex: 'whitelist_enabled', width: 110,
      render: (val, r) => (
        <Space size={4}>
          <Tag color={val ? 'green' : 'default'}>{val ? '啟用' : '關閉'}</Tag>
          {val && <Tag>{{ log_only: '只記錄', no_reply: '不回覆', full: '全自動' }[r.whitelist_mode] || r.whitelist_mode}</Tag>}
        </Space>
      ),
    },
    {
      title: '操作', width: 200,
      render: (_, r) => (
        <Space>
          <Tooltip title="重新登入（refresh token 失效時）">
            <Button size="small" icon={<LoginOutlined />} onClick={() => setLoginBot(r)} disabled={!canEdit(user)} />
          </Tooltip>
          {r.logged_in && r.is_enabled && !r.running && (
            <Tooltip title="重新啟動輪詢">
              <Button size="small" icon={<ReloadOutlined />} onClick={() => handleRestart(r)} disabled={!canEdit(user)} />
            </Tooltip>
          )}
          <Button size="small" icon={<EditOutlined />} disabled={!canEdit(user)}
            onClick={() => { setEditing(r); form.setFieldsValue({ name: r.name, poll_interval_sec: r.poll_interval_sec }) }} />
          <Popconfirm title="確定要刪除此機器人？群組設定與紀錄會一併刪除。" onConfirm={() => handleDelete(r.id)} disabled={!canEdit(user)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!canEdit(user)} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div className="page-header">
        <h2>Teams 機器人管理</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>重新整理</Button>
          {canEdit(user) && <Button type="primary" icon={<PlusOutlined />} onClick={() => setLoginBot(null)}>新增機器人</Button>}
        </Space>
      </div>

      <Alert type="info" showIcon style={{ marginBottom: 16 }}
        message="Teams 機器人使用「個人帳號輪詢」模式"
        description="以 Teams 個人帳號登入後，系統每 20 秒讀取該帳號所在群組的新訊息並自動處理。微軟限制每個帳號每分鐘 15 次呼叫（讀＋寫），超過只會延後、不會漏訊息。同一個帳號只能在一台機器上執行。" />

      <Table rowKey="id" dataSource={bots} columns={columns} loading={loading}
        pagination={{ pageSize: 10 }} locale={{ emptyText: '尚未新增任何 Teams 機器人' }} />

      {loginBot !== undefined && (
        <LoginModal bot={loginBot} onClose={() => setLoginBot(undefined)} onDone={() => load()} />
      )}

      <Modal title="編輯機器人" open={!!editing} onOk={handleEditSave} onCancel={() => setEditing(null)}
        okText="儲存" cancelText="取消" width={420}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="機器人名稱" rules={[{ required: true, message: '請輸入名稱' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="poll_interval_sec" label="輪詢間隔（秒）" extra="最低 10 秒；調低會把每分鐘 15 次的額度吃給輪詢，建議維持 20">
            <Input type="number" min={10} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

// ── 群組設定 Tab ──────────────────────────────────────────────────────────────
function GroupsTab({ user }) {
  const [bots, setBots] = useState([])
  const [botId, setBotId] = useState(null)
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [vendorGroup, setVendorGroup] = useState(null)
  const [vendorCheck, setVendorCheck] = useState(false)
  const [allowedVendors, setAllowedVendors] = useState('')
  const [singleGroup, setSingleGroup] = useState(null)
  const [singleMode, setSingleMode] = useState(false)
  const [singleName, setSingleName] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { getTeamsBots().then(r => setBots(r.data.filter(b => b.logged_in))) }, [])

  const loadGroups = async id => {
    setLoading(true)
    try { setGroups((await getTeamsGroups(id)).data) }
    catch (e) { message.error(e.response?.data?.detail || '載入群組失敗'); setGroups([]) }
    finally { setLoading(false) }
  }

  const patch = async (chatId, data, okMsg) => {
    try {
      await updateTeamsGroup(botId, chatId, data)
      setGroups(prev => prev.map(g => g.chat_id === chatId ? { ...g, ...data } : g))
      if (okMsg) message.success(okMsg)
      return true
    } catch { message.error('更新失敗'); return false }
  }

  const saveVendor = async () => {
    setSaving(true)
    const ok = await patch(vendorGroup.chat_id, {
      whitelist_vendor_check: vendorCheck, whitelist_allowed_vendors: allowedVendors.trim() || '',
    }, '廠商驗證設定已儲存')
    setSaving(false)
    if (ok) setVendorGroup(null)
  }

  const saveSingle = async () => {
    setSaving(true)
    const ok = await patch(singleGroup.chat_id, {
      single_vendor_mode: singleMode, single_vendor_name: singleName.trim() || '',
    }, '單一總代理設定已儲存')
    setSaving(false)
    if (ok) setSingleGroup(null)
  }

  const shown = search ? groups.filter(g => g.chat_name.toLowerCase().includes(search.toLowerCase())) : groups

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <Select style={{ width: 240 }} placeholder="選擇機器人" value={botId}
          onChange={id => { setBotId(id); setSearch(''); loadGroups(id) }}>
          {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
        </Select>
        {botId && (
          <>
            <Input allowClear placeholder="搜尋群組名稱" style={{ width: 240 }} value={search}
              onChange={e => setSearch(e.target.value)} prefix={<SearchOutlined style={{ color: '#bbb' }} />} />
            <Button icon={<ReloadOutlined />} onClick={() => loadGroups(botId)}>重新讀取</Button>
            <span style={{ fontSize: 12, color: '#888' }}>共 {groups.length} 個群組（即時從 Teams 讀取，每次 1 次額度）</span>
          </>
        )}
      </div>

      {!botId ? <Empty description="請先選擇機器人" style={{ padding: 48 }} />
        : loading ? <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
        : groups.length === 0 ? <Empty description="此帳號尚未加入任何群組" style={{ padding: 48 }} />
        : (
          <Table rowKey="chat_id" dataSource={shown} pagination={false} scroll={{ x: 1200, y: 520 }}
            columns={[
              {
                title: '監看', dataIndex: 'watch_enabled', width: 80,
                render: (v, r) => (
                  <Tooltip title="關閉後完全不讀取此群（可省額度）">
                    <Switch checked={v !== false} size="small" disabled={!canEdit(user)}
                      onChange={c => patch(r.chat_id, { watch_enabled: c, chat_name: r.chat_name }, c ? '已開始監看' : '已停止監看')} />
                  </Tooltip>
                ),
              },
              {
                title: '群組名稱', dataIndex: 'chat_name', width: 220, ellipsis: true,
                render: (n, r) => (
                  <div>
                    <Text strong ellipsis style={{ maxWidth: 200 }} title={n}>{n}</Text>
                    <div><Text type="secondary" style={{ fontSize: 11 }} copyable={{ text: r.chat_id, icon: <CopyOutlined style={{ fontSize: 11 }} /> }}>{r.chat_id.slice(0, 28)}…</Text></div>
                  </div>
                ),
              },
              {
                title: '最後訊息', width: 260, ellipsis: true,
                render: (_, r) => (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>{r.last_message_at ? formatDateTime(r.last_message_at) : '-'}</Text>
                    <div><Text ellipsis style={{ fontSize: 12, maxWidth: 240 }} title={r.last_message_preview}>{r.last_message_preview || ''}</Text></div>
                  </div>
                ),
              },
              {
                title: '白名單廠商驗證', width: 130,
                render: (_, r) => (
                  <Space size={6}>
                    <Tag color={r.whitelist_vendor_check ? 'blue' : 'default'}>{r.whitelist_vendor_check ? '已啟用' : '未啟用'}</Tag>
                    {canEdit(user) && (
                      <Tooltip title="廠商驗證設定">
                        <Button size="small" icon={<SafetyOutlined />}
                          onClick={() => { setVendorGroup(r); setVendorCheck(!!r.whitelist_vendor_check); setAllowedVendors(r.whitelist_allowed_vendors || '') }} />
                      </Tooltip>
                    )}
                  </Space>
                ),
              },
              {
                title: '單一總代理', width: 150,
                render: (_, r) => (
                  <Space size={6}>
                    <Tag color={r.single_vendor_mode ? 'purple' : 'default'}>{r.single_vendor_mode ? (r.single_vendor_name || '已啟用') : '未啟用'}</Tag>
                    {canEdit(user) && (
                      <Tooltip title="單一總代理設定">
                        <Button size="small" icon={<IdcardOutlined />}
                          onClick={() => { setSingleGroup(r); setSingleMode(!!r.single_vendor_mode); setSingleName(r.single_vendor_name || '') }} />
                      </Tooltip>
                    )}
                  </Space>
                ),
              },
              {
                title: 'Bo白名單添加放寬', dataIndex: 'relaxed_bo_detect', width: 130,
                render: (v, r) => (
                  <Tooltip title='開啟後，訊息只要含「whitelist/白名單」+ IP + 帳號標籤格式，即使沒提「後台」字樣也會觸發後台白名單自動處理'>
                    <Switch checked={!!v} size="small" disabled={!canEdit(user)}
                      checkedChildren="放寬" unCheckedChildren="嚴格"
                      onChange={c => patch(r.chat_id, { relaxed_bo_detect: c }, c ? 'Bo白名單添加放寬已啟用' : 'Bo白名單添加放寬已關閉')} />
                  </Tooltip>
                ),
              },
              {
                title: '自動建立工單', dataIndex: 'ticket_creation_enabled', width: 120,
                render: (v, r) => (
                  <Switch checked={v !== false} size="small" disabled={!canEdit(user)}
                    checkedChildren="開啟" unCheckedChildren="關閉"
                    onChange={c => patch(r.chat_id, { ticket_creation_enabled: c }, c ? '自動建立工單已啟用' : '自動建立工單已關閉')} />
                ),
              },
            ]}
            locale={{ emptyText: '無符合條件的群組' }}
          />
        )}

      <Modal title={`廠商驗證設定 — ${vendorGroup?.chat_name || ''}`} open={!!vendorGroup}
        onOk={saveVendor} onCancel={() => setVendorGroup(null)} okText="儲存" cancelText="取消" confirmLoading={saving} width={500}>
        <div style={{ marginBottom: 16, color: '#666', fontSize: 13 }}>
          啟用後，此群組收到的白名單申請只有解析出的廠商名稱符合允許清單時才會執行；不符合則回覆「人員將會協助確認」。
        </div>
        <div style={{ marginBottom: 16 }}>
          <Space><Switch checked={vendorCheck} onChange={setVendorCheck} checkedChildren="啟用" unCheckedChildren="關閉" /><Text>廠商驗證開關</Text></Space>
        </div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>
          允許廠商前綴 <Text type="secondary" style={{ fontWeight: 400, fontSize: 12 }}>（逗號分隔，不分大小寫，例：TitanTR1_SCFLY, VendorB）</Text>
        </div>
        <TextArea rows={4} value={allowedVendors} onChange={e => setAllowedVendors(e.target.value)} disabled={!vendorCheck} placeholder="TitanTR1_SCFLY, VendorB_Brand" />
      </Modal>

      <Modal title={`單一總代理設定 — ${singleGroup?.chat_name || ''}`} open={!!singleGroup}
        onOk={saveSingle} onCancel={() => setSingleGroup(null)} okText="儲存" cancelText="取消" confirmLoading={saving} width={500}>
        <div style={{ marginBottom: 16, color: '#666', fontSize: 13 }}>
          啟用後，當白名單申請訊息只有「後台關鍵字＋IP」而<strong>沒有帳號</strong>時，直接以下方總代理名稱比對加白。
        </div>
        <div style={{ marginBottom: 16 }}>
          <Space><Switch checked={singleMode} onChange={setSingleMode} checkedChildren="啟用" unCheckedChildren="關閉" /><Text>單一總代理開關</Text></Space>
        </div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>
          總代理名稱 <Text type="secondary" style={{ fontWeight: 400, fontSize: 12 }}>（需與後台系統中的廠商名稱完全一致，不分大小寫）</Text>
        </div>
        <Input value={singleName} onChange={e => setSingleName(e.target.value)} disabled={!singleMode} placeholder="gamius" />
      </Modal>
    </div>
  )
}

export default function TeamsBotsPage({ user }) {
  return (
    <Card>
      <Tabs
        defaultActiveKey="bots"
        items={[
          { key: 'bots', label: '機器人列表', children: <BotsTab user={user} /> },
          { key: 'groups', label: '群組設定', children: <GroupsTab user={user} /> },
        ]}
      />
    </Card>
  )
}
