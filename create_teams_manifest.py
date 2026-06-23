"""
生成 Teams App 安裝套件 (botwang_teams_app.zip)
執行後將 zip 上傳到 Teams 即可安裝機器人
"""
import json, zipfile, uuid, base64, io

BOT_ID = "6f4d94dd-d26a-4763-b07a-84dcb9408eed"
BOT_NAME = "BOTWANG"
BACKEND_URL = "https://tg-admin-backend-rm99.onrender.com"

manifest = {
    "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.16/MicrosoftTeams.schema.json",
    "manifestVersion": "1.16",
    "version": "1.0.0",
    "id": str(uuid.uuid4()),
    "packageName": "com.botwang.teamsbot",
    "developer": {
        "name": BOT_NAME,
        "websiteUrl": BACKEND_URL,
        "privacyUrl": BACKEND_URL,
        "termsOfUseUrl": BACKEND_URL
    },
    "icons": {
        "color": "color.png",
        "outline": "outline.png"
    },
    "name": {
        "short": BOT_NAME,
        "full": f"{BOT_NAME} Teams 機器人"
    },
    "description": {
        "short": f"{BOT_NAME} 智能客服機器人",
        "full": f"{BOT_NAME} Teams 智能客服機器人，支援關鍵字回覆與 AI 知識庫查詢"
    },
    "accentColor": "#1677ff",
    "bots": [
        {
            "botId": BOT_ID,
            "scopes": ["personal", "team", "groupchat"],
            "supportsFiles": False,
            "isNotificationOnly": False,
            "commandLists": [
                {
                    "scopes": ["personal", "team", "groupchat"],
                    "commands": [
                        {"title": "help", "description": "顯示說明"}
                    ]
                }
            ]
        }
    ],
    "permissions": ["identity", "messageTeamMembers"],
    "validDomains": [BACKEND_URL.replace("https://", "")]
}

# 最小的有效 PNG (藍色 192x192 簡單圖示)
COLOR_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAACXBIWXMAAAsTAAALEwEAmpwY"
    "AAAAB3RJTUUH6AYWBjMPTaG1fwAAAB1pVFh0Q29tbWVudAAAAAAAQ3JlYXRlZCB3aXRoIEdJ"
    "TVBkLmUHAAAA2ElEQVR42u3BMQEAAADCoPVP7WsIoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAeAMBuAABHgAAAABJRU5ErkJggg=="
)

OUTLINE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAACXBIWXMAAAsTAAALEwEAmpwY"
    "AAAAB3RJTUUH6AYWBjUmMtDmIgAAAB1pVFh0Q29tbWVudAAAAAAAQ3JlYXRlZCB3aXRoIEdJ"
    "TVBkLmUHAAAANklEQVRYw+3BMQEAAADCoPVP7WsIoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAeAMBuAABHgAAAABJRU5ErkJggg=="
)

color_bytes = base64.b64decode(COLOR_PNG_B64)
outline_bytes = base64.b64decode(OUTLINE_PNG_B64)

output = "botwang_teams_app.zip"
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    zf.writestr("color.png", color_bytes)
    zf.writestr("outline.png", outline_bytes)

print(f"Done: {output}")
print("Upload this zip to Teams > Apps > Manage your apps > Upload a custom app")
