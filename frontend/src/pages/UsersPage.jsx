import React, { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Tag, Typography, Switch, Checkbox, Alert,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, UserOutlined } from '@ant-design/icons'
import { getUsers, createUser, updateUser, deleteUser } from '../api'
import { formatDateTime } from '../utils/datetime'
import { PAGES, PAGE_GROUPS } from '../permissions'

const { Text } = Typography

const ROLE_COLOR = { superadmin: 'red', editor: 'blue', viewer: 'default' }
const ROLE_LABEL = { superadmin: '超級管理員', editor: '編輯員', viewer: '檢視者' }

const allPerms = level => Object.fromEntries(PAGES.map(p => [p.key, level]))

// 頁面權限勾選表：檢視者只有「可查看」欄；編輯員多一欄「可編輯」（勾可編輯會自動勾可查看）
function PermissionEditor({ role, perms, onChange }) {
  const isEditor = role === 'editor'
  const viewOf = key => !!perms[key]
  const editOf = key => isEditor && perms[key] === 'edit'

  const setView = (key, checked) => {
    const next = { ...perms }
    if (checked) next[key] = next[key] || 'view'
    else delete next[key]
    onChange(next)
  }
  const setEdit = (key, checked) => onChange({ ...perms, [key]: checked ? 'edit' : 'view' })
  const setAll = (keys, field, checked) => {
    const next = { ...perms }
    keys.forEach(k => {
      if (field === 'view') { if (checked) next[k] = next[k] || 'view'; else delete next[k] }
      else next[k] = checked ? 'edit' : (next[k] ? 'view' : undefined)
    })
    Object.keys(next).forEach(k => next[k] === undefined && delete next[k])
    onChange(next)
  }
  const headerBox = (keys, field) => {
    const vals = keys.map(k => (field === 'view' ? viewOf(k) : editOf(k)))
    const all = vals.every(Boolean)
    return (
      <Checkbox checked={all} indeterminate={!all && vals.some(Boolean)}
        onChange={e => setAll(keys, field, e.target.checked)} />
    )
  }

  const allKeys = PAGES.map(p => p.key)
  const rows = PAGE_GROUPS.flatMap(g => [
    { rowKey: `g-${g}`, group: g, keys: PAGES.filter(p => p.group === g).map(p => p.key) },
    ...PAGES.filter(p => p.group === g).map(p => ({ rowKey: p.key, page: p })),
  ])
  const columns = [
    {
      title: '頁面', key: 'label',
      render: (_, r) => (r.group
        ? <Text strong>{r.group}</Text>
        : <span style={{ paddingLeft: 16 }}>{r.page.label}</span>),
    },
    {
      title: <Space size={6}>{headerBox(allKeys, 'view')}可查看</Space>, key: 'view', width: 110, align: 'center',
      render: (_, r) => (r.group
        ? headerBox(r.keys, 'view')
        : <Checkbox checked={viewOf(r.page.key)} onChange={e => setView(r.page.key, e.target.checked)} />),
    },
    ...(isEditor ? [{
      title: <Space size={6}>{headerBox(allKeys, 'edit')}可編輯</Space>, key: 'edit', width: 110, align: 'center',
      render: (_, r) => (r.group
        ? headerBox(r.keys, 'edit')
        : <Checkbox checked={editOf(r.page.key)} onChange={e => setEdit(r.page.key, e.target.checked)} />),
    }] : []),
  ]
  return (
    <Table rowKey="rowKey" dataSource={rows} columns={columns} size="small" pagination={false}
      scroll={{ y: 340 }} bordered
      onRow={r => (r.group ? { style: { background: '#fafafa' } } : {})} />
  )
}

function permSummary(u) {
  if (u.role === 'superadmin') return <Tag color="red">全部頁面（含帳號管理）</Tag>
  const pp = u.page_permissions || {}
  const view = Object.keys(pp).length
  const edit = Object.values(pp).filter(v => v === 'edit').length
  return (
    <Space size={4} wrap>
      <Tag color={view ? 'green' : 'default'}>可查看 {view}/{PAGES.length}</Tag>
      {u.role === 'editor' && <Tag color={edit ? 'blue' : 'default'}>可編輯 {edit}</Tag>}
      {!u.permissions_customized && <Text type="secondary" style={{ fontSize: 12 }}>（未設定，預設全部）</Text>}
    </Space>
  )
}

export default function UsersPage({ user: currentUser }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [perms, setPerms] = useState({})
  const [form] = Form.useForm()
  const role = Form.useWatch('role', form)

  const load = async () => {
    setLoading(true)
    try {
      const res = await getUsers()
      setUsers(res.data)
    } catch {
      message.error('載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openAdd = () => {
    setEditingUser(null)
    form.resetFields()
    setPerms(allPerms('edit'))         // 新帳號預設全部勾選，檢視者儲存時自動視為「可查看」
    setModalOpen(true)
  }

  const openEdit = (u) => {
    setEditingUser(u)
    form.setFieldsValue({ username: u.username, email: u.email, role: u.role })
    setPerms(u.role === 'superadmin' ? allPerms('edit') : { ...(u.page_permissions || {}) })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    const permissions = values.role === 'superadmin' ? undefined
      : Object.fromEntries(Object.entries(perms).map(([k, v]) => [k, values.role === 'editor' ? v : 'view']))
    try {
      if (editingUser) {
        const payload = { email: values.email, role: values.role, permissions }
        if (values.password) payload.password = values.password
        await updateUser(editingUser.id, payload)
        message.success('已更新')
      } else {
        await createUser({ ...values, permissions })
        message.success('已新增')
      }
      setModalOpen(false)
      load()
    } catch (err) {
      message.error(err.response?.data?.detail || '操作失敗')
    }
  }

  const handleToggleActive = async (u, checked) => {
    if (u.id === currentUser?.id) { message.warning('無法停用自己的帳號'); return }
    try {
      await updateUser(u.id, { is_active: checked })
      load()
    } catch {
      message.error('操作失敗')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteUser(id)
      message.success('已刪除')
      load()
    } catch (err) {
      message.error(err.response?.data?.detail || '刪除失敗')
    }
  }

  const columns = [
    {
      title: '帳號',
      dataIndex: 'username',
      render: (name, record) => (
        <Space>
          <UserOutlined />
          <Text strong>{name}</Text>
          {record.id === currentUser?.id && <Tag color="geekblue">本人</Tag>}
        </Space>
      ),
    },
    { title: 'Email', dataIndex: 'email' },
    {
      title: '角色',
      dataIndex: 'role',
      render: role => <Tag color={ROLE_COLOR[role]}>{ROLE_LABEL[role]}</Tag>,
    },
    { title: '頁面權限', key: 'perms', render: (_, record) => permSummary(record) },
    {
      title: '啟用',
      dataIndex: 'is_active',
      width: 80,
      render: (val, record) => (
        <Switch checked={val} size="small"
          onChange={checked => handleToggleActive(record, checked)}
          disabled={record.id === currentUser?.id} />
      ),
    },
    {
      title: '建立時間',
      dataIndex: 'created_at',
      width: 160,
      render: t => formatDateTime(t),
    },
    {
      title: '操作',
      width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm
            title="確定刪除此帳號？"
            onConfirm={() => handleDelete(record.id)}
            disabled={record.id === currentUser?.id}
          >
            <Button size="small" danger icon={<DeleteOutlined />}
              disabled={record.id === currentUser?.id} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <div className="page-header">
        <h2>帳號管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
          新增帳號
        </Button>
      </div>

      <Table
        rowKey="id"
        dataSource={users}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editingUser ? '編輯帳號' : '新增帳號'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText={editingUser ? '儲存' : '新增'}
        cancelText="取消"
        width={620}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {!editingUser && (
            <Form.Item name="username" label="帳號" rules={[{ required: true, message: '請輸入帳號' }]}>
              <Input placeholder="登入用帳號" />
            </Form.Item>
          )}
          <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email', message: '請輸入有效 Email' }]}>
            <Input placeholder="example@email.com" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '請選擇角色' }]}>
            <Select placeholder="選擇角色">
              <Select.Option value="superadmin">超級管理員</Select.Option>
              <Select.Option value="editor">編輯員</Select.Option>
              <Select.Option value="viewer">檢視者</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="password"
            label={editingUser ? '新密碼（留空則不變更）' : '密碼'}
            rules={editingUser ? [] : [{ required: true, message: '請輸入密碼' }]}
          >
            <Input.Password placeholder={editingUser ? '留空則不變更密碼' : '設定密碼'} />
          </Form.Item>

          <Form.Item label="頁面權限" style={{ marginBottom: 0 }}>
            {!role ? (
              <Text type="secondary">請先選擇角色</Text>
            ) : role === 'superadmin' ? (
              <Alert type="info" showIcon message="超級管理員固定擁有全部頁面的查看與編輯權限，並可使用「帳號管理」。" />
            ) : (
              <>
                <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                  {role === 'editor'
                    ? '勾選「可查看」的頁面才會出現在選單；同時勾選「可編輯」才能在該頁修改設定（勾選可編輯會自動勾選可查看）。'
                    : '檢視者只能查看：勾選的頁面才會出現在選單，所有頁面都無法修改。'}
                </Text>
                <PermissionEditor role={role} perms={perms} onChange={setPerms} />
              </>
            )}
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
