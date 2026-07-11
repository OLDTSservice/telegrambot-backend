import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Typography, theme } from 'antd'
import {
  RobotOutlined, KeyOutlined, BookOutlined, BarChartOutlined,
  UserOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  SendOutlined, TeamOutlined, StopOutlined, LineChartOutlined, MessageOutlined,
  SafetyOutlined,
} from '@ant-design/icons'
import { getMe } from './api'
import LoginPage from './pages/LoginPage'
import BotsPage from './pages/BotsPage'
import RulesPage from './pages/RulesPage'
import KnowledgePage from './pages/KnowledgePage'
import StatsPage from './pages/StatsPage'
import UsersPage from './pages/UsersPage'
import TeamsBotsPage from './pages/TeamsBotsPage'
import TeamsRulesPage from './pages/TeamsRulesPage'
import TeamsKnowledgePage from './pages/TeamsKnowledgePage'
import TelegramIgnorePage from './pages/TelegramIgnorePage'
import TeamsIgnorePage from './pages/TeamsIgnorePage'
import TelegramReplyStatsPage from './pages/TelegramReplyStatsPage'
import TelegramLivePage from './pages/TelegramLivePage'
import WhitelistPage from './pages/WhitelistPage'
import TeamsReplyStatsPage from './pages/TeamsReplyStatsPage'

const { Sider, Header, Content } = Layout
const { Text } = Typography

const ROLE_LABEL = { superadmin: '超級管理員', editor: '編輯員', viewer: '檢視者' }

export default function App() {
  const [user, setUser] = useState(null)
  const [collapsed, setCollapsed] = useState(false)
  const [openKeys, setOpenKeys] = useState(['telegram'])
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
    navigate('/telegram/bots')
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
    {
      key: 'telegram',
      icon: <SendOutlined />,
      label: 'Telegram 機器人',
      children: [
        { key: '/telegram/bots', icon: <RobotOutlined />, label: '機器人管理' },
        { key: '/telegram/rules', icon: <KeyOutlined />, label: '關鍵字規則' },
        { key: '/telegram/knowledge', icon: <BookOutlined />, label: '知識庫管理' },
        { key: '/telegram/ignores', icon: <StopOutlined />, label: '忽略名單' },
        { key: '/telegram/reply-stats', icon: <LineChartOutlined />, label: '回覆統計' },
        { key: '/telegram/live', icon: <MessageOutlined />, label: '即時對話管控' },
        { key: '/telegram/whitelist', icon: <SafetyOutlined />, label: '後台白名單處理' },
      ],
    },
    {
      key: 'teams',
      icon: <TeamOutlined />,
      label: 'Teams 機器人',
      children: [
        { key: '/teams/bots', icon: <RobotOutlined />, label: '機器人管理' },
        { key: '/teams/rules', icon: <KeyOutlined />, label: '關鍵字規則' },
        { key: '/teams/knowledge', icon: <BookOutlined />, label: '知識庫管理' },
        { key: '/teams/ignores', icon: <StopOutlined />, label: '忽略名單' },
        { key: '/teams/reply-stats', icon: <LineChartOutlined />, label: '回覆統計' },
      ],
    },
    { key: '/stats', icon: <BarChartOutlined />, label: '使用量統計' },
    ...(user?.role === 'superadmin'
      ? [{ key: '/users', icon: <UserOutlined />, label: '帳號管理' }]
      : []),
  ]

  const selectedKey = location.pathname

  const userMenu = {
    items: [
      { key: 'logout', icon: <LogoutOutlined />, label: '登出', danger: true },
    ],
    onClick: ({ key }) => { if (key === 'logout') handleLogout() },
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} trigger={null} width={220} style={{ background: '#001529' }}>
        <div style={{
          height: 56, display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 20px', borderBottom: '1px solid #ffffff18',
        }}>
          <RobotOutlined style={{ color: '#1677ff', fontSize: 22 }} />
          {!collapsed && (
            <Text style={{ color: '#fff', marginLeft: 10, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>
              機器人後台管理
            </Text>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={collapsed ? [] : openKeys}
          onOpenChange={keys => setOpenKeys(keys)}
          items={menuItems}
          onClick={({ key }) => { if (key.startsWith('/')) navigate(key) }}
          style={{ marginTop: 8 }}
        />
      </Sider>

      <Layout>
        <Header style={{
          background: '#fff', padding: '0 20px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: '1px solid #f0f0f0', height: 56,
        }}>
          <div onClick={() => setCollapsed(!collapsed)} style={{ cursor: 'pointer', fontSize: 18, color: '#555' }}>
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
          <Dropdown menu={userMenu} placement="bottomRight">
            <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar size={32} icon={<UserOutlined />} style={{ background: '#1677ff' }} />
              {user && (
                <span style={{ fontSize: 13 }}>
                  {user.username}
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>{ROLE_LABEL[user.role]}</Text>
                </span>
              )}
            </div>
          </Dropdown>
        </Header>

        <Content style={{ padding: 24 }}>
          <Routes>
            <Route path="/telegram/bots" element={<BotsPage user={user} />} />
            <Route path="/telegram/rules" element={<RulesPage user={user} />} />
            <Route path="/telegram/knowledge" element={<KnowledgePage user={user} />} />
            <Route path="/telegram/ignores" element={<TelegramIgnorePage user={user} />} />
            <Route path="/telegram/reply-stats" element={<TelegramReplyStatsPage />} />
            <Route path="/telegram/live" element={<TelegramLivePage user={user} />} />
            <Route path="/telegram/whitelist" element={<WhitelistPage user={user} />} />
            <Route path="/teams/bots" element={<TeamsBotsPage user={user} />} />
            <Route path="/teams/rules" element={<TeamsRulesPage user={user} />} />
            <Route path="/teams/knowledge" element={<TeamsKnowledgePage user={user} />} />
            <Route path="/teams/ignores" element={<TeamsIgnorePage user={user} />} />
            <Route path="/teams/reply-stats" element={<TeamsReplyStatsPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/users" element={<UsersPage user={user} />} />
            <Route path="*" element={<Navigate to="/telegram/bots" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
