"""台灣時區（Asia/Taipei, UTC+8）共用工具。

Render 伺服器系統時間是 UTC，所有需要「今天日期」做統計分桶的地方
（回覆統計、使用量統計等）若直接用 date.today()，會用 UTC 日曆日切分，
與前端（瀏覽器台灣時區）認知的日期不一致，導致台灣時間每天 00:00–08:00
的資料被歸類到前一天。統一改用這裡的 taipei_today()。
"""
from datetime import datetime, timezone, timedelta

TAIPEI_TZ = timezone(timedelta(hours=8))


def taipei_today():
    """回傳台灣時區的今天日期（date 物件）"""
    return datetime.now(TAIPEI_TZ).date()
