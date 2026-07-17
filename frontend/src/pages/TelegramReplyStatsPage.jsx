import React, { useEffect, useState, useCallback } from 'react'
import {
  Card, Row, Col, Select, DatePicker, Table, Tag, Space,
  Typography, Statistic, Spin, Empty, Button,
} from 'antd'
import { TrophyOutlined, MessageOutlined, RobotOutlined, FileTextOutlined, CheckCircleOutlined } from '@ant-design/icons'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line,
} from 'recharts'
import dayjs from 'dayjs'
import { getTelegramGroupStats, getTelegramTrend, getBots, getTicketCounts } from '../api'

const { Text, Title } = Typography
const { RangePicker } = DatePicker

const CHAT_TYPE_TAG = {
  private: { color: 'blue', label: '私聊' },
  group: { color: 'green', label: '群組' },
  supergroup: { color: 'purple', label: '超級群組' },
  channel: { color: 'orange', label: '頻道' },
}

// 快捷時間範圍
const PRESETS = [
  { label: '今日',   getRange: () => [dayjs(), dayjs()] },
  { label: '昨日',   getRange: () => [dayjs().subtract(1,'day'), dayjs().subtract(1,'day')] },
  { label: '近7日',  getRange: () => [dayjs().subtract(6,'day'), dayjs()] },
  { label: '近30日', getRange: () => [dayjs().subtract(29,'day'), dayjs()] },
  { label: '本月',   getRange: () => [dayjs().startOf('month'), dayjs().endOf('month')] },
  { label: '上個月', getRange: () => [dayjs().subtract(1,'month').startOf('month'), dayjs().subtract(1,'month').endOf('month')] },
  { label: '今年',   getRange: () => [dayjs().startOf('year'), dayjs().endOf('year')] },
  { label: '去年',   getRange: () => [dayjs().subtract(1,'year').startOf('year'), dayjs().subtract(1,'year').endOf('year')] },
]

export default function TelegramReplyStatsPage() {
  const today = dayjs()
  const [dateRange, setDateRange] = useState([today.startOf('month'), today])
  const [activePreset, setActivePreset] = useState('本月')
  const [botId, setBotId] = useState(null)
  const [bots, setBots] = useState([])
  const [rankData, setRankData] = useState([])
  const [trendData, setTrendData] = useState([])
  const [ticketCounts, setTicketCounts] = useState({ kb_tickets: 0, whitelist_tickets: 0 })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getBots().then(r => setBots(r.data)).catch(() => {})
  }, [])

  useEffect(() => { load() }, [dateRange, botId])

  const buildParams = useCallback(() => {
    const [from, to] = dateRange
    return {
      date_from: from.format('YYYY-MM-DD'),
      date_to: to.format('YYYY-MM-DD'),
      bot_id: botId || undefined,
    }
  }, [dateRange, botId])

  const load = async () => {
    setLoading(true)
    try {
      const params = buildParams()
      const [rankRes, trendRes, tcRes] = await Promise.all([
        getTelegramGroupStats(params),
        getTelegramTrend(params),
        getTicketCounts(params),
      ])
      setRankData(rankRes.data)
      setTrendData(trendRes.data)
      setTicketCounts(tcRes.data)
    } catch {}
    finally { setLoading(false) }
  }

  const handlePreset = (preset) => {
    setActivePreset(preset.label)
    setDateRange(preset.getRange())
  }

  const handleRangeChange = (dates) => {
    if (dates) {
      setActivePreset(null)
      setDateRange(dates)
    }
  }

  const totalReplies = rankData.reduce((s, r) => s + r.reply_count, 0)

  const rankColumns = [
    {
      title: '排名', width: 60,
      render: (_, __, idx) => (
        <span style={{ fontWeight: 700, color: idx < 3 ? ['#FFD700','#C0C0C0','#CD7F32'][idx] : '#888' }}>
          {idx < 3 ? ['🥇','🥈','🥉'][idx] : `#${idx + 1}`}
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
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {/* 快捷按鈕 */}
          <Space wrap>
            <span style={{ fontWeight: 600, color: '#333' }}>快捷選擇：</span>
            {PRESETS.map(p => (
              <Button
                key={p.label}
                size="small"
                type={activePreset === p.label ? 'primary' : 'default'}
                onClick={() => handlePreset(p)}
              >
                {p.label}
              </Button>
            ))}
          </Space>
          {/* 自訂時間範圍 + 機器人篩選 */}
          <Space wrap>
            <span style={{ fontWeight: 600, color: '#333' }}>自訂範圍：</span>
            <RangePicker
              value={dateRange}
              onChange={handleRangeChange}
              allowClear={false}
              format="YYYY/MM/DD"
            />
            <span style={{ marginLeft: 8, fontWeight: 600, color: '#333' }}>機器人：</span>
            <Select
              value={botId}
              onChange={setBotId}
              style={{ width: 180 }}
              allowClear
              placeholder="全部機器人"
            >
              <Select.Option value={null}>全部機器人</Select.Option>
              {bots.map(b => <Select.Option key={b.id} value={b.id}>{b.name}</Select.Option>)}
            </Select>
          </Space>
        </Space>
      </Card>

      {/* 摘要卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="總回覆次數" value={totalReplies}
              prefix={<MessageOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="活躍群組數" value={rankData.length}
              prefix={<RobotOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="知識庫建立工單數"
              value={ticketCounts.kb_tickets}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="白名單建立工單數"
              value={ticketCounts.whitelist_tickets}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#13c2c2' }}
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
                      <YAxis type="category" dataKey="chat_name" width={110} tick={{ fontSize: 11 }} />
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
