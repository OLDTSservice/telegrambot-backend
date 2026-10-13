import React, { useState } from 'react'
import { Button, Popconfirm, Tag, Tooltip, Typography, message } from 'antd'
import { RollbackOutlined } from '@ant-design/icons'
import { formatDateTime } from '../utils/datetime'

const { Text } = Typography

// Teams 處理紀錄的「已回覆」欄：顯示是否已回覆，並可收回機器人送出的回覆。
// onRecall 由頁面傳入（白名單／查輸贏各自呼叫自己的收回 API），成功後頁面重新載入紀錄。
export default function TeamsReplyCell({ record, canEdit, onRecall, note }) {
  const [loading, setLoading] = useState(false)

  if (record.reply_recalled_at) {
    return (
      <Tooltip title={`收回時間：${formatDateTime(record.reply_recalled_at)}`}>
        <Tag color="default">已收回</Tag>
      </Tooltip>
    )
  }
  if (!record.reply_sent) return '-'

  const recallable = !!(record.reply_msg_id || record.reply_client_msg_id)
  if (!recallable) {
    return <Tooltip title="收回功能上線前送出的回覆，無法從後台收回">是</Tooltip>
  }

  const doRecall = async () => {
    setLoading(true)
    try {
      await onRecall(record)
      message.success('已從 Teams 群組收回這則回覆')
    } catch (e) {
      message.error(e.response?.data?.detail || '收回失敗')
    } finally {
      setLoading(false)
    }
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      是
      {canEdit && (
        <Popconfirm
          title="收回這則回覆？"
          description={
            <div style={{ maxWidth: 280 }}>
              會從 Teams 群組刪除機器人送出的這則回覆。<br />
              {note && <Text type="warning">{note}</Text>}
            </div>
          }
          onConfirm={doRecall} okText="收回" cancelText="取消" okButtonProps={{ danger: true }}
        >
          <Tooltip title="收回回覆">
            <Button size="small" type="text" danger icon={<RollbackOutlined />} loading={loading} />
          </Tooltip>
        </Popconfirm>
      )}
    </span>
  )
}
