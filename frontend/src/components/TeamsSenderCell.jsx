import React from 'react'
import { Typography, Button, Popconfirm, Tooltip, message } from 'antd'
import { StopOutlined } from '@ant-design/icons'
import { createTeamsIgnore } from '../api'

const { Text } = Typography

// Teams 處理紀錄的「發送者」欄：顯示名稱＋可複製的 MRI，並可一鍵加入忽略名單。
// 優先用 MRI 加入（對方改名也不會失效）；舊紀錄沒有 MRI 時才用顯示名稱。
export default function TeamsSenderCell({ botId, sender, senderMri, canEdit }) {
  if (!sender && !senderMri) return '-'
  const identifier = senderMri || sender

  const addIgnore = async () => {
    try {
      await createTeamsIgnore({ bot_id: botId, identifier, note: `${sender || identifier}（從處理紀錄加入）` })
      message.success(`已將「${sender || identifier}」加入忽略名單`)
    } catch (e) {
      message.error(e.response?.data?.detail || '加入忽略名單失敗')
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4 }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <Text ellipsis style={{ maxWidth: '100%' }} title={sender}>{sender || '-'}</Text>
        {senderMri && (
          <div>
            <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }} copyable={{ text: senderMri }}
              ellipsis title={senderMri}>
              {senderMri}
            </Text>
          </div>
        )}
      </div>
      {canEdit && (
        <Popconfirm
          title="加入忽略名單？"
          description={
            <div style={{ maxWidth: 260 }}>
              之後將完全略過此帳號的訊息（白名單與查輸贏都不處理）。<br />
              識別碼：<Text code>{identifier}</Text>
              {!senderMri && <div><Text type="warning">此筆紀錄沒有 MRI，將以顯示名稱加入，對方改名後會失效。</Text></div>}
            </div>
          }
          onConfirm={addIgnore} okText="加入" cancelText="取消"
        >
          <Tooltip title="加入忽略名單">
            <Button size="small" type="text" icon={<StopOutlined />} />
          </Tooltip>
        </Popconfirm>
      )}
    </div>
  )
}
