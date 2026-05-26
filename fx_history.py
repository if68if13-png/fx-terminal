#!/usr/bin/env python3
"""
FX Terminal - 履歴記録スクリプト
毎日15時の自動更新時に fx_history.json に追記
"""
import json, os, datetime

ANALYSIS_DIR = os.path.expanduser("~/Documents/FX分析")
HISTORY_JSON = os.path.join(ANALYSIS_DIR, "fx_history.json")
FX_DATA_JSON = os.path.join(ANALYSIS_DIR, "fx_data.json")
OUTLOOK_JSON = os.path.join(ANALYSIS_DIR, "fx_outlook.json")
ADMIN_JSON   = os.path.join(ANALYSIS_DIR, "fx_admin.json")

def main():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"📅 履歴記録: {today}")

    # 各JSONを読み込む
    try:
        fx_data  = json.load(open(FX_DATA_JSON,  encoding="utf-8"))
        outlook  = json.load(open(OUTLOOK_JSON,  encoding="utf-8"))
        admin    = json.load(open(ADMIN_JSON,     encoding="utf-8")) if os.path.exists(ADMIN_JSON) else {}
    except Exception as e:
        print(f"  ⚠️ 読み込みエラー: {e}")
        return

    # 既存の履歴を読み込む
    if os.path.exists(HISTORY_JSON):
        history = json.load(open(HISTORY_JSON, encoding="utf-8"))
    else:
        history = []

    # 同じ日付があれば上書き、なければ追加
    entry = {
        "date":    today,
        "overall": outlook.get("overall", ""),
        "risk":    outlook.get("risk_mode", "") + " | " + outlook.get("key_risk", ""),
        "pairs":   outlook.get("pairs", {}),
        "scores":  fx_data.get("scores", {}),
        "memo":    admin.get("diary", ""),
        "cb_stance": outlook.get("cb_stance", {}),
    }

    # 同日エントリを更新 or 追加
    dates = [h["date"] for h in history]
    if today in dates:
        history[dates.index(today)] = entry
        print(f"  → {today} を更新")
    else:
        history.append(entry)
        print(f"  → {today} を追加（累計{len(history)}日）")

    # 日付降順でソート（新しい順）
    history.sort(key=lambda x: x["date"], reverse=True)

    # 保存（最大365日分）
    history = history[:365]
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存完了: {HISTORY_JSON}")

if __name__ == "__main__":
    main()
