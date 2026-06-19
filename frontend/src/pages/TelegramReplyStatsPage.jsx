import React, { useEffect, useState } from 'react'
import {
  Card, Row, Col, Select, DatePicker, Table, Tag, Space,
  Typography, Statistic, Spin, Empty,
} from 'antd'
import { TrophyOutlined, MessageOutlined, RobotOutlined } from '@ant-design/icons'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line,
} from 'recharts'
import dayjs from 'dayjs'
import { getTelegramGroupStats, getTelegramTrend, getBots } from '../api'

const { Text, Title } = Typography

const PERIOD_OPTIONS = [
  { label: '每日', value: 'daily' },
  { label: '每月', value: 'monthly' },
  { label: '每年', value: 'yearly' },
]

const CHAT_TYPE_TAG = {
  private: { color: 'blue', label: '私聊' },
  group: { color: 'green', label: '群組' },
  supergroup: { color: 'purple', label: '超級群組' },
  channel: { color: 'orange', label: '頻道' },
}

function periodValue(period) {
  const now = dayjs()
  if (period === 'daily') return now.format('YYYY-MM-DD')
  if (period === 'monthly') return now.format('YYYY-MM')
  return now.format('YYYY')
}

export default function TelegramReplyStatsPage() {
  const [period, setPeriod] = useState('monthly')
  const [value, setValue] = useState(periodValue('monthly'))
  const [botId, setBotId] = useState(null)
  const [bots, setBots] = useState([])
  const [rankData, setRankData] = useState([])
  const [trendData, setTrendData] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getBots().then(r => setBots(r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    load()
  }, [period, value, botId])

  const load = async () => {
    setLoading(true)
    try {
      const [rankRes, trendRes] = await Promise.all([
        getTelegramGroupStats(period, value, botId),
        getTelegramTrend(period, value, botId),
      ])
      setRankData(rankRes.data)
      setTrendData(trendRes.data)
    } catch { }
    finally { setLoading(false) }
  }

  const totalReplies = rankData.reduce((s, r) => s + r.reply_count, 0)

  const handlePeriodChange = (p) => {
    setPeriod(p)
    setValue(periodValue(p))
  }

  const handleDateChange = (_, dateStr) => {
    if (dateStr) setValue(dateStr)
  }

  const rankColumns = [
    {
      title: '排名', width: 60,
      render: (_, __, idx) => (
        <span style={{ fontWeight: 700, color: idx < 3 ? ['#FFD700', '#C0C0C0', '#CD7F32'][idx] : '#888' }}>
          {idx < 3 ? ['🥇', '🥈', '🥉'][idx] : `#${idx + 1}`}
        </span>
      ),
    },
    {
      title: '群組 / 聊天室', dataIndex: 'chat_name',
      render: (name, record) => (
        <Space>
          <Text strong>{name}</Text>
          {CHAT_TYPE_TAG[record.chat_type] && (
            <Tag color={CHAT_TYPE_TAG[record.chat_type].color} style={{ fontSize: 11 }}>
              {CHAT_TYPE_TAG[record.chat_type].label}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: '回覆次數', dataIndex: 'reply_count', width: 120,
      render: v => <Text strong style={{ color: '#1677ff', fontSize: 15 }}>{v.toLocaleString()}</Text>,
    },
    {
      title: '佔比', width: 100,
      render: (_, record) => (
        <Text type="secondary">
          {totalReplies > 0 ? ((record.reply_count / totalReplies) * 100).toFixed(1) : 0}%
        </Text>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 20 }}>
        <MessageOutlined style={{ marginRight: 8, color: '#1677ff' }} />
        Telegram 機器人回覆統計
      </Title>

      {/* 篩選列 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>統計週期：</span>
          <Select value={period} onChange={handlePeriodChange} style={{ width: 100 }}
            options={PERIOD_OPTIONS} />

          {period === 'daily' && (
            <DatePicker value={dayjs(value)} onChange={handleDateChange}
              format="YYYY-MM-DD" allowClear={false} />
          )}
          {period === 'monthly' && (
            <DatePicker.MonthPicker value={dayjs(value)} onChange={handleDateChange}
              format="YYYY-MM" allowClear={false} />
          )}
          {period === 'yearly' && (
            <DatePicker.YearPicker value={dayjs(value)} onChange={handleDateChange}
              format="YYYY" allowClear={false} />
          )}

          <span style={{ marginLeft: 8 }}>機器人：</span>
          <Select value={botId} onChange={setBotId} style={{ width: 160 }}
            placeholder="全部機器人" allowClear>
            {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
          </Select>
        </Space>
      </Card>

      {/* 摘要卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic title="總回覆次數" value={totalReplies}
              prefix={<MessageOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="活躍群組數" value={rankData.length}
              prefix={<RobotOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="最活躍群組"
              value={rankData[0]?.chat_name || '—'}
              prefix={<TrophyOutlined style={{ color: '#FFD700' }} />}
              valueStyle={{ fontSize: 16 }}
            />
          </Card>
        </Col>
      </Row>

      <Spin spinning={loading}>
        <Row gutter={16}>
          {/* 趨勢折線圖 */}
          <Col span={24} style={{ marginBottom: 16 }}>
            <Card title="回覆趨勢">
              {trendData.length === 0
                ? <Empty description="此期間無資料" />
                : (
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip formatter={v => [`${v} 次`, '回覆次數']} />
                      <Line type="monotone" dataKey="reply_count" stroke="#1677ff"
                        strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
            </Card>
          </Col>

          {/* 排行 Bar Chart */}
          <Col xs={24} lg={12} style={{ marginBottom: 16 }}>
            <Card title="群組回覆排行（圖表）">
              {rankData.length === 0
                ? <Empty description="此期間無資料" />
                : (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={rankData.slice(0, 10)} layout="vertical"
                      margin={{ left: 20, right: 30 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                      <YAxis type="category" dataKey="chat_name" width={110}
                        tick={{ fontSize: 11 }} />
                      <Tooltip formatter={v => [`${v} 次`, '回覆次數']} />
                      <Bar dataKey="reply_count" fill="#1677ff" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
            </Card>
          </Col>

          {/* 排行表格 */}
          <Col xs={24} lg={12} style={{ marginBottom: 16 }}>
            <Card title={`群組回覆排行（共 ${rankData.length} 個）`}>
              <Table
                rowKey="chat_id"
                dataSource={rankData}
                columns={rankColumns}
                pagination={{ pageSize: 8, size: 'small' }}
                size="small"
                locale={{ emptyText: '此期間無回覆記錄' }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
