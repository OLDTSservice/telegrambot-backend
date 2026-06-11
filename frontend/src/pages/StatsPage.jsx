import React, { useEffect, useState } from 'react'
import {
  Card, Row, Col, Statistic, Select, Spin, Empty, Typography,
} from 'antd'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ThunderboltOutlined, ApiOutlined, CalendarOutlined, RobotOutlined } from '@ant-design/icons'
import { getStats } from '../api'

const { Text } = Typography

const COLORS = ['#1677ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2']

export default function StatsPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [days, setDays] = useState(30)

  const load = async () => {
    setLoading(true)
    try {
      const res = await getStats(days)
      setStats(res.data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [days])

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>

  return (
    <div>
      <div className="page-header">
        <h2>使用量統計</h2>
        <Select value={days} onChange={setDays} style={{ width: 130 }}>
          <Select.Option value={7}>最近 7 天</Select.Option>
          <Select.Option value={30}>最近 30 天</Select.Option>
          <Select.Option value={90}>最近 90 天</Select.Option>
        </Select>
      </div>

      {/* 摘要卡片 */}
      <Row gutter={16} style={{ marginBottom: 20 }}>
        {[
          { title: '今日 Token 用量', value: stats?.total_tokens_today ?? 0, icon: <ThunderboltOutlined />, color: '#1677ff' },
          { title: '本月 Token 用量', value: stats?.total_tokens_month ?? 0, icon: <CalendarOutlined />, color: '#52c41a' },
          { title: '今日請求次數', value: stats?.total_requests_today ?? 0, icon: <ApiOutlined />, color: '#faad14' },
          { title: '本月請求次數', value: stats?.total_requests_month ?? 0, icon: <RobotOutlined />, color: '#f5222d' },
        ].map(({ title, value, icon, color }) => (
          <Col span={6} key={title}>
            <Card className="stat-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 10,
                  background: `${color}18`, display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  fontSize: 20, color,
                }}>
                  {icon}
                </div>
                <Statistic title={title} value={value} valueStyle={{ fontSize: 22 }} />
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16} style={{ marginBottom: 20 }}>
        {/* 每日 Token 折線圖 */}
        <Col span={16}>
          <Card title="每日 Token 用量趨勢">
            {stats?.daily?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={stats.daily} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="input_tokens" name="輸入 Token" stroke="#1677ff" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="output_tokens" name="輸出 Token" stroke="#52c41a" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="total_tokens" name="總計" stroke="#faad14" dot={false} strokeWidth={2} strokeDasharray="4 2" />
                </LineChart>
              </ResponsiveContainer>
            ) : <Empty description="暫無資料" />}
          </Card>
        </Col>

        {/* 各機器人 Token 圓餅圖 */}
        <Col span={8}>
          <Card title="各機器人 Token 分佈">
            {stats?.by_bot?.length ? (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={stats.by_bot}
                      dataKey="total_tokens"
                      nameKey="bot_name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ bot_name, percent }) =>
                        `${bot_name} ${(percent * 100).toFixed(0)}%`
                      }
                      labelLine={false}
                    >
                      {stats.by_bot.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(val, name) => [`${val} tokens`, name]} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ marginTop: 8 }}>
                  {stats.by_bot.map((b, i) => (
                    <div key={b.bot_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '2px 0' }}>
                      <span style={{ color: COLORS[i % COLORS.length] }}>● {b.bot_name}</span>
                      <Text type="secondary">{b.total_tokens.toLocaleString()} tokens</Text>
                    </div>
                  ))}
                </div>
              </>
            ) : <Empty description="暫無資料" />}
          </Card>
        </Col>
      </Row>

      {/* 每日請求次數長條圖 */}
      <Card title="每日請求次數">
        {stats?.daily?.length ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stats.daily} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="request_count" name="請求次數" fill="#1677ff" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <Empty description="暫無資料" />}
      </Card>
    </div>
  )
}
