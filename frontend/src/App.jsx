import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Typography, message } from 'antd'
import {
  RobotOutlined, KeyOutlined, BookOutlined, BarChartOutlined,
  UserOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
} from '@ant-design/icons'
import { getMe } from './api'
import LoginPage from './pages/LoginPage'
import BotsPage from './pages/BotsPage'
import RulesPage from './pages/RulesPage'
import KnowledgePage from './pages/KnowledgePage'
import StatsPage from './pages/StatsPage'
import UsersPage from './pages/UsersPage'

const { Sider, Header, Content } = Layout
const { Text } = Typography

const ROLE_LABEL = { superadmin: '超級管理員', editor: '編輯員', viewer: '檢視者' }

export default function App() {
  const [user, setUser] = useState(null)
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      getMe().then(r => setUser(r.data)).catch(() => {
        localStorage.removeItem('token')
      })
    }
  }, [])

  const handleLogin = (userData) => {
    setUser(userData)
    navigate('/bots')
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setUser(null)
    navigate('/login')
  }

  if (!localStorage.getItem('token') && location.pathname !== '/login') {
    return <Navigate to="/login" replace />
  }

  if (location.pathname === '/login') {
    return <LoginPage onLogin={handleLogin} />
  }

  const menuItems = [
    { key: '/bots', icon: <RobotOutlined />, label: '機器人管理' },
    { key: '/rules', icon: <KeyOutlined />, label: '關鍵字規則' },
    { key: '/knowledge', icon: <BookOutlined />, label: '知識庫管理' },
    { key: '/stats', icon: <BarChartOutlined />, label: '使用量統計' },
    ...(user?.role === 'superadmin' ? [{ key: '/users', icon: <UserOutlined />, label: '帳號管理' }] : []),
  ]

  const userMenu = {
    items: [
      { key: 'logout', icon: <LogoutOutlined />, label: '登出', danger: true },
    ],
    onClick: ({ key }) => { if (key === 'logout') handleLogout() },
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        trigger={null}
        width={220}
        style={{ background: '#001529' }}
      >
        <div style={{
          height: 56, display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 20px', borderBottom: '1px solid #ffffff18',
        }}>
          <RobotOutlined style={{ color: '#1677ff', fontSize: 22 }} />
          {!collapsed && (
            <Text style={{ color: '#fff', marginLeft: 10, fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap' }}>
              TG 後台管理
            </Text>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ marginTop: 8 }}
        />
      </Sider>

      <Layout>
        <Header style={{
          background: '#fff', padding: '0 20px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: '1px solid #f0f0f0', height: 56,
        }}>
          <div
            onClick={() => setCollapsed(!collapsed)}
            style={{ cursor: 'pointer', fontSize: 18, color: '#555' }}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>

          <Dropdown menu={userMenu} placement="bottomRight">
            <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar size={32} icon={<UserOutlined />} style={{ background: '#1677ff' }} />
              {user && (
                <span style={{ fontSize: 13 }}>
                  {user.username}
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>
                    {ROLE_LABEL[user.role]}
                  </Text>
                </span>
              )}
            </div>
          </Dropdown>
        </Header>

        <Content style={{ padding: 24 }}>
          <Routes>
            <Route path="/bots" element={<BotsPage user={user} />} />
            <Route path="/rules" element={<RulesPage user={user} />} />
            <Route path="/knowledge" element={<KnowledgePage user={user} />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/users" element={<UsersPage user={user} />} />
            <Route path="*" element={<Navigate to="/bots" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
