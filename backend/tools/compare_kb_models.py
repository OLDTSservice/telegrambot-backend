"""比較知識庫問答在不同模型（例如 Haiku 4.5 與 Haiku 5.5）上的表現，確認原本的提示詞規則都有被遵守。

用法（在專案根目錄、PowerShell）：
    # 1) 只估算會呼叫幾次、大概花多少錢，不會呼叫 API
    & ".\\backend\\venv\\Scripts\\python.exe" ".\\backend\\tools\\compare_kb_models.py" --dry-run

    # 2) 規則測試（內建假資料，每個模型跑一輪，會呼叫 API、花少量費用）
    & ".\\backend\\venv\\Scripts\\python.exe" ".\\backend\\tools\\compare_kb_models.py"

    # 3) 另外用真實知識庫與真實問題比較（--kb 是上傳用的檔案：txt / xlsx；--questions 每行一個問題）
    & ".\\backend\\venv\\Scripts\\python.exe" ".\\backend\\tools\\compare_kb_models.py" --kb "知識庫.txt" --questions "問題.txt"

規則測試用的知識庫與問題都是內建的假資料，涵蓋提示詞裡的規則：
  1 只回知識庫直接對應的答案、1a 清單逐項檢查、2 申請單/表單視為提交資料、3 依問題語言回覆（簡/繁/英）、
  3a 英文問題必須翻成英文、3b 多語言版本只留目標語言、4 沒有答案只回固定字串、基本資訊模式只答素材/基本資料。
結果會印出每個模型每一題的通過/失敗，以及 token 與預估費用。真實資料的比較結果寫到報告檔（預設
compare_kb_report.md，會含問題與回覆內容，請自行保管、不要提交進版控）。

API 金鑰讀 backend/.env 的 ANTHROPIC_API_KEY，腳本不會印出金鑰。
"""
import argparse
import logging
import os
import re
import sys
import time

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, BACKEND)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BACKEND, ".env"))
except Exception:
    pass

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from services import ai_service  # noqa: E402

# 每百萬 token 單價（USD）：(輸入, 輸出)；僅供預估。Haiku 5.5 的價格是單次提示詞 100K token 以內的價格。
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

CHUNKS = [
    "Q: 請提供API文件\nAPI文件 API document\nA: 請參考下方連結\n轉帳錢包API文件\nhttps://example.com/transfer-api\n"
    "單一錢包API文件\nhttps://example.com/single-api",
    "支援 Buy Bonus 的遊戲清單：\n521 Super Ace\n523 Fortune Coins\n524 Money Coming\n525 Golden Empire",
    "Q: 遊戲素材\n素材 game asset\nA: 您好，請參考以下網址\nhttps://example.com/asset-zh\n"
    "Hello, please refer to the link below\nhttps://example.com/asset-en",
    "Q: 支持哪些货币\n币种\nA: 目前支持 MYR、THB、USD 三种货币。",
    "Q: API 使用的時區\nA: API 與後台使用的時區是 GMT+8。",
]

_CJK = re.compile(r"[一-鿿]")
_TRAD_ONLY = set("貨幣種進時區後台")
_SIMP_ONLY = set("货币种进时区后台")


def has_cjk(s):
    return bool(_CJK.search(s))


def case(name, question, check, asset_mode=False, rule=""):
    return {"name": name, "question": question, "check": check, "asset_mode": asset_mode, "rule": rule}


CASES = [
    case("繁中問 API 文件", "請提供API文件",
         lambda r: r is not None and "transfer-api" in r and "single-api" in r and has_cjk(r), rule="1/3"),
    case("英文問 API 文件（必須翻成英文）", "please provide api document",
         lambda r: r is not None and "transfer-api" in r and "single-api" in r and not has_cjk(r), rule="3a"),
    case("印尼文問 API 文件（一律英文）", "bagaimana cara mendapatkan dokumen api?",
         lambda r: r is not None and "transfer-api" in r and not has_cjk(r), rule="3"),
    case("清單內有該項目", "Does Fortune Coins support Buy Bonus?",
         lambda r: r is not None and not has_cjk(r) and re.search(r"yes|support", r, re.I) is not None, rule="1a"),
    case("清單內沒有該項目", "Does Lucky Neko support Buy Bonus?", lambda r: r is None, rule="1a/4"),
    case("與知識庫無關的問題", "今天台北天氣如何？", lambda r: r is None, rule="4"),
    case("申請單／表單", "1. 商戶名字：abc\n2. 幣種：MYR\n3. 回調地址：https://example.com/cb",
         lambda r: r is None, rule="2"),
    case("多語言版本：中文問只留中文", "請提供遊戲素材",
         lambda r: r is not None and "asset-zh" in r and "asset-en" not in r, rule="3b"),
    case("多語言版本：英文問只留英文", "please share the game asset",
         lambda r: r is not None and "asset-en" in r and "asset-zh" not in r and not has_cjk(r), rule="3b"),
    case("簡體問用簡體答", "支持哪些币种？",
         lambda r: r is not None and "MYR" in r and has_cjk(r) and not (set(r) & _TRAD_ONLY), rule="3"),
    case("繁體問用繁體答（知識庫是簡體）", "支援哪些幣別？",
         lambda r: r is not None and "MYR" in r and has_cjk(r) and not (set(r) & _SIMP_ONLY), rule="3"),
    case("英文問時區（知識庫是中文）", "What timezone does the API use?",
         lambda r: r is not None and "GMT+8" in r and not has_cjk(r), rule="3a"),
    case("基本資訊模式：非素材問題", "我的帳號被鎖住了，可以幫我解鎖嗎？", lambda r: r is None, asset_mode=True, rule="0"),
    case("基本資訊模式：素材問題", "請提供遊戲素材",
         lambda r: r is not None and "asset-zh" in r, asset_mode=True, rule="0"),
]


LEAKS = {}  # 各模型回覆夾帶 reminder 標籤、被程式移除的次數


def call(model, question, chunks, asset_mode):
    """以指定模型呼叫與正式環境相同的 _call_claude，回傳 (reply, in, out, cache_read, cache_write, 秒數, api_error)"""
    os.environ["KB_MODEL"] = model
    t0 = time.time()
    before = ai_service.LEAKED_TAG_COUNT
    res = ai_service._call_claude(question, chunks, 0, asset_mode=asset_mode)
    dt = time.time() - t0
    LEAKS[model] = LEAKS.get(model, 0) + (ai_service.LEAKED_TAG_COUNT - before)
    reply, i, o, cr, cw = res
    # _call_claude 在 API 例外時回 (None,0,0,0,0)，與「沒有答案」靠 token 數區分（有答案/無答案都至少有輸入 token）
    api_error = (i == 0 and o == 0)
    return reply, i, o, cr, cw, dt, api_error


def cost(model, i, o, cr=0, cw=0):
    pi, po = PRICES.get(model, (0, 0))
    return (i * pi + o * po + cr * pi * 0.1 + cw * pi * 1.25) / 1_000_000


def load_real_chunks(path):
    ext = os.path.splitext(path)[1].lower()
    return ai_service._chunk_text(ai_service._extract_text(path, ext))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="claude-haiku-4-5-20251001,claude-haiku-5-5")
    ap.add_argument("--repeat", type=int, default=1, help="每一題每個模型重複次數（觀察穩定度）")
    ap.add_argument("--dry-run", action="store_true", help="只估算，不呼叫 API")
    ap.add_argument("--kb", help="真實知識庫檔案（txt/xlsx，格式同後台上傳）")
    ap.add_argument("--questions", help="真實問題檔，每行一個問題")
    ap.add_argument("--report", default="compare_kb_report.md")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    real_chunks, real_qs = None, []
    if args.kb and args.questions:
        real_chunks = load_real_chunks(args.kb)
        real_qs = [l.strip() for l in open(args.questions, encoding="utf-8") if l.strip()]

    sys_chars = 2300  # 系統提示詞約略字元數
    rule_ctx = sum(len(c) for c in CHUNKS) + sys_chars
    real_ctx = (sum(len(c) for c in real_chunks) + sys_chars) if real_chunks else 0
    n_rule = len(CASES) * args.repeat * len(models)
    n_real = len(real_qs) * len(models)
    print(f"模型：{models}（努力程度 KB_EFFORT={os.getenv('KB_EFFORT') or 'low'}）")
    print(f"規則測試：{len(CASES)} 題 × {args.repeat} 次 × {len(models)} 個模型 = {n_rule} 次呼叫")
    if real_chunks:
        print(f"真實資料：{len(real_qs)} 題 × {len(models)} 個模型 = {n_real} 次呼叫，知識庫 {len(real_chunks)} 段／約 {real_ctx} 字元")
    # 粗估：中英混合約 1 token ≈ 1.5 字元；輸出每次約 300 token（5.5 加上思考可能更多，取 800）
    for m in models:
        out_est = 300 if "4-5" in m else 800
        est = (n_rule // len(models)) * cost(m, rule_ctx / 1.5, out_est) + (n_real // max(len(models), 1)) * cost(m, real_ctx / 1.5, out_est)
        print(f"  預估費用 {m}：約 ${est:.3f}")
    if args.dry_run:
        print("（--dry-run：未呼叫 API）")
        return
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("找不到 ANTHROPIC_API_KEY（backend/.env），無法呼叫 API")
        sys.exit(1)

    # ── 規則測試 ─────────────────────────────────────────────
    summary = {m: {"pass": 0, "total": 0, "in": 0, "out": 0, "cost": 0.0, "secs": 0.0, "err": 0} for m in models}
    print("\n=== 規則測試 ===")
    for c in CASES:
        row = []
        for m in models:
            ok_n = 0
            last = None
            for _ in range(args.repeat):
                reply, i, o, cr, cw, dt, err = call(m, c["question"], CHUNKS, c["asset_mode"])
                s = summary[m]
                s["total"] += 1
                s["in"] += i
                s["out"] += o
                s["cost"] += cost(m, i, o, cr, cw)
                s["secs"] += dt
                if err:
                    s["err"] += 1
                ok = (not err) and bool(c["check"](reply))
                s["pass"] += ok
                ok_n += ok
                last = reply
            row.append(f"{m.split('-20')[0][7:]}: {'PASS' if ok_n == args.repeat else f'FAIL({ok_n}/{args.repeat})'}")
            if ok_n != args.repeat:
                print(f"    ↳ [{m}] 回覆：{(last or '(無答案/無回覆)')[:200]!r}")
        print(f"[{c['rule']:>4}] {c['name']}：" + "  |  ".join(row))

    print("\n=== 規則測試總結 ===")
    for m, s in summary.items():
        print(f"{m}: 通過 {s['pass']}/{s['total']}，API 失敗 {s['err']} 次，token in={s['in']} out={s['out']}，"
              f"平均 {s['secs'] / max(s['total'], 1):.1f} 秒/次，費用約 ${s['cost']:.4f}")

    # ── 真實資料比較 ──────────────────────────────────────────
    if real_chunks and real_qs:
        print("\n=== 真實資料比較 ===")
        lines = ["# 知識庫模型比較報告\n", f"模型：{', '.join(models)}\n"]
        diff_na = diff_text = 0
        tot = {m: [0, 0, 0.0] for m in models}
        for q in real_qs:
            outs = {}
            for m in models:
                reply, i, o, cr, cw, dt, err = call(m, q, real_chunks, False)
                outs[m] = (reply, err)
                tot[m][0] += i
                tot[m][1] += o
                tot[m][2] += cost(m, i, o, cr, cw)
            na = {m: (r is None) for m, (r, e) in outs.items()}
            same_na = len(set(na.values())) == 1
            same_text = len({(r or "").strip() for r, e in outs.values()}) == 1
            diff_na += (not same_na)
            diff_text += (not same_text)
            flag = "一致" if same_text else ("有答案/無答案不一致" if not same_na else "回覆文字不同")
            lines.append(f"\n## {q[:80]}\n- 結果：**{flag}**")
            for m, (r, e) in outs.items():
                lines.append(f"- `{m}`：{'API失敗' if e else (r if r is not None else '（無答案）')}")
        lines.append(f"\n---\n共 {len(real_qs)} 題；有答案/無答案不一致 {diff_na} 題；回覆文字不同 {diff_text} 題。\n")
        for m, (i, o, c_) in tot.items():
            lines.append(f"- {m}：token in={i} out={o}，費用約 ${c_:.4f}")
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"{len(real_qs)} 題；有答案/無答案不一致 {diff_na} 題；回覆文字不同 {diff_text} 題；報告：{args.report}")
    print("夾帶 reminder 標籤（已被程式移除）次數：" + "、".join(f"{m}={LEAKS.get(m, 0)}" for m in models))


if __name__ == "__main__":
    main()
