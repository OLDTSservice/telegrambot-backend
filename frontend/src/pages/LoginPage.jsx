import React, { useState } from 'react'
import { Form, Input, Button, Card, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons'
import { login, getMe } from '../api'

const { Title, Text } = Typography

export default function LoginPage({ onLogin }) {
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (values) => {
    setLoading(true)
    try {
      const res = await login(values.username, values.password)
      localStorage.setItem('token', res.data.access_token)
      const meRes = await getMe()
      message.success('登入成功')
      onLogin(meRes.data)
    } catch (err) {
      message.error(err.response?.data?.detail || '登入失敗，請確認帳號密碼')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#f5f6fa',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Card style={{ width: 380, boxShadow: '0 4px 20px rgba(0,0,0,.08)', borderRadius: 12 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <RobotOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          <Title level={4} style={{ margin: '12px 0 4px' }}>Telegram 機器人後台</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>請登入以繼續使用</Text>
        </div>

        <Form layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="username" rules={[{ required: true, message: '請輸入帳號' }]}>
            <Input prefix={<UserOutlined />} placeholder="帳號" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '請輸入密碼' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密碼" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={loading}>
            登入
          </Button>
        </Form>

        <Text type="secondary" style={{ fontSize: 12, display: 'block', textAlign: 'center', marginTop: 16 }}>
          預設帳號：admin / admin123
        </Text>
      </Card>
    </div>
  )
}
