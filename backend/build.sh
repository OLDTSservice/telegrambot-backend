#!/bin/bash
set -e
pip install -r requirements.txt
# 將 Chromium 安裝到 project 目錄內，避免 Render 每次重啟後 /opt/render/.cache 被清空
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/pw-browsers
playwright install chromium
