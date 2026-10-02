import React, { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Typography, theme, Result, Button, Spin } from 'antd'
import {
  RobotOutlined, KeyOutlined, BookOutlined, BarChartOutlined,
  UserOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  SendOutlined, TeamOutlined, StopOutlined, LineChartOutlined, MessageOutlined,
  SafetyOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons'
import { getMe } from './api'
import { pageByPath, canViewPage, firstAllowedPath, pageUser } from './permissions'
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
import NetwinPage from './pages/NetwinPage'
import TeamsReplyStatsPage from './pages/TeamsReplyStatsPage'
import TeamsWhitelistPage from './pages/TeamsWhitelistPage'
import TeamsNetwinPage from './pages/TeamsNetwinPage'
import TelegramBotAdminPage from './pages/TelegramBotAdminPage'

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
    navigate(firstAllowedPath(userData) || '/no-access')
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
        { key: '/telegram/bot-admins', icon: <SafetyCertificateOutlined />, label: '機器人管理員名單' },
        { key: '/telegram/reply-stats', icon: <LineChartOutlined />, label: '回覆工單統計' },
        { key: '/telegram/live', icon: <MessageOutlined />, label: '即時對話管控' },
        { key: '/telegram/whitelist', icon: <SafetyOutlined />, label: '後台白名單處理' },
        { key: '/telegram/netwin', icon: <LineChartOutlined />, label: '查輸贏回覆' },
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
        { key: '/teams/reply-stats', icon: <LineChartOutlined />, label: '回覆工單統計' },
        { key: '/teams/whitelist', icon: <SafetyOutlined />, label: '後台白名單處理' },
        { key: '/teams/netwin', icon: <LineChartOutlined />, label: '查輸贏回覆' },
      ],
    },
    { key: '/stats', icon: <BarChartOutlined />, label: '使用量統計' },
    ...(user?.role === 'superadmin'
      ? [{ key: '/users', icon: <UserOutlined />, label: '帳號管理' }]
      : []),
  ]
    // 依頁面權限只顯示能查看的頁面；整組都沒有可看頁面時連群組一起隱藏
    .map(item => {
      if (!item.children) return item
      const children = item.children.filter(c => canViewPage(user, pageByPath(c.key)?.key))
      return children.length ? { ...item, children } : null
    })
    .filter(item => item && (item.children || item.key === '/users' || canViewPage(user, pageByPath(item.key)?.key)))

  // 路由守門：沒有該頁查看權限就顯示無權限頁；傳給頁面的 user 已依該頁權限換算角色（見 permissions.js）
  const guard = (path, render) => {
    if (!user) return <div style={{ textAlign: 'center', padding: 80 }}><Spin /></div>
    const key = pageByPath(path)?.key
    if (!canViewPage(user, key)) return <NoAccess user={user} />
    return render(pageUser(user, key))
  }

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
            <Route path="/telegram/bots" element={guard('/telegram/bots', u => <BotsPage user={u} />)} />
            <Route path="/telegram/rules" element={guard('/telegram/rules', u => <RulesPage user={u} />)} />
            <Route path="/telegram/knowledge" element={guard('/telegram/knowledge', u => <KnowledgePage user={u} />)} />
            <Route path="/telegram/ignores" element={guard('/telegram/ignores', u => <TelegramIgnorePage user={u} />)} />
            <Route path="/telegram/bot-admins" element={guard('/telegram/bot-admins', u => <TelegramBotAdminPage user={u} />)} />
            <Route path="/telegram/reply-stats" element={guard('/telegram/reply-stats', () => <TelegramReplyStatsPage />)} />
            <Route path="/telegram/live" element={guard('/telegram/live', u => <TelegramLivePage user={u} />)} />
            <Route path="/telegram/whitelist" element={guard('/telegram/whitelist', u => <WhitelistPage user={u} />)} />
            <Route path="/telegram/netwin" element={guard('/telegram/netwin', u => <NetwinPage user={u} />)} />
            <Route path="/teams/bots" element={guard('/teams/bots', u => <TeamsBotsPage user={u} />)} />
            <Route path="/teams/rules" element={guard('/teams/rules', u => <TeamsRulesPage user={u} />)} />
            <Route path="/teams/knowledge" element={guard('/teams/knowledge', u => <TeamsKnowledgePage user={u} />)} />
            <Route path="/teams/ignores" element={guard('/teams/ignores', u => <TeamsIgnorePage user={u} />)} />
            <Route path="/teams/reply-stats" element={guard('/teams/reply-stats', () => <TeamsReplyStatsPage />)} />
            <Route path="/teams/whitelist" element={guard('/teams/whitelist', u => <TeamsWhitelistPage user={u} />)} />
            <Route path="/teams/netwin" element={guard('/teams/netwin', u => <TeamsNetwinPage user={u} />)} />
            <Route path="/stats" element={guard('/stats', () => <StatsPage />)} />
            <Route path="/users" element={
              !user ? <div style={{ textAlign: 'center', padding: 80 }}><Spin /></div>
                : user.role === 'superadmin' ? <UsersPage user={user} /> : <NoAccess user={user} />
            } />
            <Route path="*" element={
              !user ? <div style={{ textAlign: 'center', padding: 80 }}><Spin /></div>
                : firstAllowedPath(user) ? <Navigate to={firstAllowedPath(user)} replace /> : <NoAccess user={user} />
            } />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}


function NoAccess({ user }) {
  const navigate = useNavigate()
  const target = firstAllowedPath(user)
  return (
    <Result
      status="403"
      title="沒有權限"
      subTitle={target ? '您的帳號沒有此頁面的查看權限。' : '您的帳號目前沒有任何頁面的查看權限，請聯絡超級管理員設定。'}
      extra={target && <Button type="primary" onClick={() => navigate(target)}>前往可使用的頁面</Button>}
    />
  )
}
