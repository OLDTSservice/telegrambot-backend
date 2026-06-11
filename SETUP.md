# Telegram 機器人後台管理系統 — 安裝說明

## 系統需求
- Python 3.10+
- Node.js 18+

---

## 後端安裝

```bash
cd backend

# 建立虛擬環境（建議）
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux

# 安裝套件
pip install -r requirements.txt

# 設定環境變數（複製後填入 API Key）
copy .env.example .env
# 編輯 .env 填入 ANTHROPIC_API_KEY

# 啟動伺服器
python -m uvicorn main:app --reload --port 8000
```

後端啟動後自動建立資料庫及預設管理員帳號：
- 帳號：`admin`
- 密碼：`admin123`

---

## 前端安裝

```bash
cd frontend
npm install
npm run dev
```

前端預設運行於 http://localhost:5173

---

## 一鍵啟動（Windows）

直接執行根目錄的 `start.bat`

---

## API 文件

後端啟動後可至 http://localhost:8000/docs 查看完整 Swagger API 文件

---

## 功能說明

| 功能 | 說明 |
|------|------|
| 帳號管理 | 超級管理員可新增/編輯/刪除帳號，設定角色（超級管理員/編輯員/檢視者） |
| 機器人管理 | 新增 Telegram Bot Token，啟用後自動開始接收訊息 |
| 關鍵字規則 | 設定觸發關鍵字與自動回覆內容，每條規則可獨立啟停 |
| 知識庫管理 | 上傳 PDF/Word/Excel/TXT 文件，AI 根據內容回覆相關問題 |
| 使用量統計 | 查看每日/每月 Token 消耗與各機器人分佈圖表 |

---

## 角色權限

| 功能 | 超級管理員 | 編輯員 | 檢視者 |
|------|-----------|--------|--------|
| 查看所有功能 | ✅ | ✅ | ✅ |
| 新增/編輯/刪除 | ✅ | ✅ | ❌ |
| 帳號管理 | ✅ | ❌ | ❌ |
