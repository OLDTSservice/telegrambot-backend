import React, { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, Select,
  Popconfirm, message, Space, Card, Tag, Typography, Switch,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, UserOutlined } from '@ant-design/icons'
import { getUsers, createUser, updateUser, deleteUser } from '../api'

const { Text } = Typography

const ROLE_COLOR = { superadmin: 'red', editor: 'blue', viewer: 'default' }
const ROLE_LABEL = { superadmin: '超級管理員', editor: '編輯員', viewer: '檢視者' }

export default function UsersPage({ user: currentUser }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [form] = Form.useForm()

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
    setModalOpen(true)
  }

  const openEdit = (u) => {
    setEditingUser(u)
    form.setFieldsValue({ username: u.username, email: u.email, role: u.role })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingUser) {
        const payload = { email: values.email, role: values.role }
        if (values.password) payload.password = values.password
        await updateUser(editingUser.id, payload)
        message.success('已更新')
      } else {
        await createUser(values)
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
      render: t => new Date(t).toLocaleString('zh-TW'),
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
        </Form>
      </Modal>
    </Card>
  )
}
