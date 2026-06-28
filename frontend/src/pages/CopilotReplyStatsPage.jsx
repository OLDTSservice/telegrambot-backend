import React, { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Select, DatePicker, Table, Typography, Space, message } from 'antd'
import { RobotOutlined, BarChartOutlined, TeamOutlined } from '@ant-design/icons'
import { getCopilotGroupStats, getCopilotTrend, getCopilotBots } from '../api'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import dayjs from 'dayjs'

const { Text } = Typography

export default function CopilotReplyStatsPage() {
  const [stats, setStats] = useState([])
  const [trend, setTrend] = useState([])
  const [bots, setBots] = useState([])
  const [period, setPeriod] = useState('daily')
  const [dateValue, setDateValue] = useState(dayjs().format('YYYY-MM-DD'))
  const [botId, setBotId] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [sRes, tRes, bRes] = await Promise.all([
        getCopilotGroupStats(period, dateValue, botId),
        getCopilotTrend(period, dateValue, botId),
        getCopilotBots(),
      ])
      setStats(sRes.data); setTrend(tRes.data); setBots(bRes.data)
    } catch { message.error('載入失敗') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [period, dateValue, botId])

  const total = stats.reduce((s, r) => s + r.reply_count, 0)
  const top = stats[0]

  const pickerProps = {
    daily: { picker: 'date', format: 'YYYY-MM-DD' },
    monthly: { picker: 'month', format: 'YYYY-MM' },
    yearly: { picker: 'year', format: 'YYYY' },
  }[period]

  const columns = [
    { title: '排名', render: (_, __, i) => i + 1, width: 60 },
    { title: '對話名稱', dataIndex: 'conversation_name' },
    { title: '回覆次數', dataIndex: 'reply_count', sorter: (a, b) => b.reply_count - a.reply_count },
  ]

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}><Card><Statistic title="總回覆次數" value={total} prefix={<BarChartOutlined />} valueStyle={{ color: '#7c3aed' }} /></Card></Col>
        <Col span={8}><Card><Statistic title="活躍對話數" value={stats.length} prefix={<TeamOutlined />} /></Card></Col>
        <Col span={8}><Card><Statistic title="最活躍對話" value={top?.conversation_name || '-'} prefix={<RobotOutlined />} /></Card></Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select value={period} onChange={v => { setPeriod(v); setDateValue(v === 'daily' ? dayjs().format('YYYY-MM-DD') : v === 'monthly' ? dayjs().format('YYYY-MM') : dayjs().format('YYYY')) }}>
            <Select.Option value="daily">每日</Select.Option>
            <Select.Option value="monthly">每月</Select.Option>
            <Select.Option value="yearly">每年</Select.Option>
          </Select>
          <DatePicker {...pickerProps} value={dayjs(dateValue)} onChange={d => d && setDateValue(d.format(pickerProps.format))} allowClear={false} />
          <Select style={{ width: 160 }} placeholder="所有機器人" allowClear value={botId} onChange={setBotId}>
            {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
          </Select>
        </Space>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey="reply_count" stroke="#7c3aed" name="回覆次數" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card title="對話回覆排名（Top 10）">
        <Row gutter={16}>
          <Col span={12}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stats.slice(0, 10)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis dataKey="conversation_name" type="category" width={120} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="reply_count" fill="#7c3aed" name="回覆次數" />
              </BarChart>
            </ResponsiveContainer>
          </Col>
          <Col span={12}>
            <Table rowKey="conversation_id" dataSource={stats.slice(0, 10)} columns={columns} loading={loading}
              pagination={false} size="small" />
          </Col>
        </Row>
      </Card>
    </div>
  )
}
