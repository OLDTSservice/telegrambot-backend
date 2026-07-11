#!/bin/bash
set -e
pip install -r requirements.txt
# Render 環境已有 Chromium 所需系統套件，不需要 --with-deps
playwright install chromium
