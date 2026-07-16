import React, { useEffect, useState } from 'react'
import {
  Card, Row, Col, Statistic, Select, Spin, Empty, Typography, Tag, Tooltip as AntTooltip,
} from 'antd'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ThunderboltOutlined, ApiOutlined, CalendarOutlined, RobotOutlined, DollarOutlined } from '@ant-design/icons'
import { getStats } from '../api'
import api from '../api'

const { Text } = Typography

const COLORS = ['#1677ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2']

// claude-haiku-4-5 定價（USD / 1M tokens）
const PRICE = {
  input: 0.80,
  output: 4.00,
  cache_write: 1.00,
  cache_read: 0.08,
}

function calcUSD(input, output, cacheRead, cacheWrite) {
  return (
    (input * PRICE.input +
     output * PRICE.output +
     cacheRead * PRICE.cache_read +
     cacheWrite * PRICE.cache_write) / 1_000_000
  )
}

export default function StatsPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [days, setDays] = useState(30)
  const [recentQueries, setRecentQueries] = useState([])

  const load = async () => {
    setLoading(true)
    try {
      const [statsRes, recentRes] = await Promise.all([
        getStats(days),
        api.get('/stats/recent-queries', { params: { limit: 10 } }),
      ])
      setStats(statsRes.data)
      setRecentQueries(recentRes.data)
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
        {/* 本月預估費用 */}
        {recentQueries.length > 0 && (() => {
          const monthUSD = recentQueries.reduce((sum, q) =>
            sum + calcUSD(q.input_tokens, q.output_tokens, q.cache_read_tokens, q.cache_write_tokens), 0)
          return (
            <Col span={6} key="usd">
              <Card className="stat-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: 10,
                    background: '#13c2c218', display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                    fontSize: 20, color: '#13c2c2',
                  }}>
                    <DollarOutlined />
                  </div>
                  <Statistic
                    title="最近 10 筆合計費用"
                    value={`$${monthUSD.toFixed(4)}`}
                    valueStyle={{ fontSize: 22, color: '#13c2c2' }}
                    suffix="USD"
                  />
                </div>
              </Card>
            </Col>
          )
        })()}
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
      <Card title="每日請求次數" style={{ marginBottom: 20 }}>
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

      {/* 最近 10 筆查詢 Token 紀錄 */}
      <Card title="最近 10 筆知識庫查詢 Token 紀錄">
        {recentQueries.length === 0 ? (
          <Empty description="尚無查詢紀錄" />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#fafafa', textAlign: 'left' }}>
                  {['時間', '群組', '問題', 'Input', 'Output', '快取讀取', '快取寫入', '實際計費', '費用 (USD)'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentQueries.map((q, i) => {
                  const billed = q.input_tokens + q.output_tokens + Math.round(q.cache_read_tokens * 0.1) + Math.round(q.cache_write_tokens * 1.25)
                  const usd = calcUSD(q.input_tokens, q.output_tokens, q.cache_read_tokens, q.cache_write_tokens)
                  return (
                    <tr key={q.id} style={{ background: i % 2 === 0 ? 'white' : '#fafafa' }}>
                      <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', color: '#888', fontSize: 11 }}>
                        {new Date(q.created_at).toLocaleString('zh-TW')}
                      </td>
                      <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                        <Text style={{ fontSize: 12 }}>{q.chat_name}</Text>
                      </td>
                      <td style={{ padding: '8px 12px', maxWidth: 200 }}>
                        <AntTooltip title={q.question}>
                          <Text ellipsis style={{ maxWidth: 180, fontSize: 12 }}>{q.question}</Text>
                        </AntTooltip>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                        <Tag color="blue">{q.input_tokens}</Tag>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                        <Tag color="green">{q.output_tokens}</Tag>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                        <Tag color="purple">{q.cache_read_tokens.toLocaleString()}</Tag>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                        <Tag color="orange">{q.cache_write_tokens.toLocaleString()}</Tag>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                        <AntTooltip title="Input + Output + 快取讀取×10% + 快取寫入×125%（等效 token 數）">
                          <Tag color="red">{billed.toLocaleString()}</Tag>
                        </AntTooltip>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                        <AntTooltip title={`Input $${(q.input_tokens*PRICE.input/1e6).toFixed(5)} + Output $${(q.output_tokens*PRICE.output/1e6).toFixed(5)} + Cache R $${(q.cache_read_tokens*PRICE.cache_read/1e6).toFixed(5)} + Cache W $${(q.cache_write_tokens*PRICE.cache_write/1e6).toFixed(5)}`}>
                          <Tag color="cyan">${usd.toFixed(5)}</Tag>
                        </AntTooltip>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
