#!/usr/bin/env python3
import anthropic, json, datetime, os, re, time

ANALYSIS_DIR = os.environ.get("SAVE_DIR", os.path.dirname(os.path.abspath(__file__)))
FX_DATA_JSON = os.path.join(ANALYSIS_DIR, "fx_data.json")
OUTLOOK_JSON = os.path.join(ANALYSIS_DIR, "fx_outlook.json")
TARGET_PAIRS = ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "WTI", "SP500"]

def load_fundamental_data():
    if not os.path.exists(FX_DATA_JSON):
        print("  fx_data.json が見つかりません")
        return None
    with open(FX_DATA_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def load_admin_data():
    admin_path = os.path.join(ANALYSIS_DIR, "fx_admin.json")
    if not os.path.exists(admin_path):
        return {}
    with open(admin_path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_prompt(data):
    today = datetime.datetime.now().strftime("%Y年%m月%d日")
    news_text = "\n".join(f"- [{n.get('source','')}] {n.get('title','')} / {n.get('summary','')[:150]}" for n in data.get("news",[])[:20]) or "なし"
    cot_text = "\n".join(f"- {c}: net {d.get('net',0):+,} ({d.get('bias','')})" for c,d in data.get("cot",{}).items()) or "取得なし"
    scores = data.get("scores", {})
    score_text = "\n".join(f"- {c}: {s:+d}" for c,s in sorted(scores.items(), key=lambda x:-x[1]))
    pair_text = "\n".join(f"- {p['pair']}: {p['direction']} (差{p.get('diff',0):+d})" for p in data.get("pairs",[]))
    admin = load_admin_data()
    fedwatch = admin.get("fedwatch", "")
    admin_text = f"FedWatch: {fedwatch}" if fedwatch else "（未入力）"
    rates = data.get("rates", {})
    rates_text = f"""- FF金利: {rates.get('US_FF','N/A')}%
- 米10年債: {rates.get('US_10Y','N/A')}%
- 日本10年債: {rates.get('JP_10Y','N/A')}%
- 独10年債: {rates.get('DE_10Y','N/A')}%
- 英10年債: {rates.get('GB_10Y','N/A')}%
- 豪10年債: {rates.get('AU_10Y','N/A')}%
- USDJPY金利差(米-日): {rates.get('DIFF_USDJPY','N/A')}%
- EURUSD金利差(独-米): {rates.get('DIFF_EURUSD','N/A')}%
- GBPUSD金利差(英-米): {rates.get('DIFF_GBPUSD','N/A')}%
- AUDUSD金利差(豪-米): {rates.get('DIFF_AUDUSD','N/A')}%"""
    return f"""あなたはFXスイングトレード専門のシニアアナリストです。
今日は{today}です。以下の実データをもとに分析してください。

【最新ニュース】
{news_text}

【COTレポート】
{cot_text}

【通貨強弱スコア(-5〜+5)】
{score_text}

【FedWatch所感（人間による市場分析）】
{admin_text}

【実際の金利データ（FRED）】
{rates_text}

【ペア判定】
{pair_text}

対象: USDJPY/EURUSD/GBPUSD/AUDUSD のスイングトレード向けに分析。WTI原油・S&P500についても長期/中期/短期の方向性を分析。
以下のJSON形式のみで返答。説明文・マークダウン不要:

{{
  "overall": "相場全体まとめ(40字以内)",
  "risk_mode": "リスクオン/リスクオフ/中立",
  "key_risk": "最重要リスクイベント(60字以内)",
  "cb_stance": {{
    "FRB": "タカ派/中立/ハト派+理由(30字)",
    "BOJ": "タカ派/中立/ハト派+理由(30字)",
    "ECB": "タカ派/中立/ハト派+理由(30字)",
    "RBA": "タカ派/中立/ハト派+理由(30字)",
    "BOE": "タカ派/中立/ハト派+理由(30字)"
  }},
  "pairs": {{
    "USDJPY": {{
      "long_view": "長期方向",
      "long_reason": "根拠(50字)",
      "mid_view": "中期方向",
      "mid_reason": "根拠(50字)",
      "short_view": "短期方向",
      "short_reason": "根拠(50字)"
    }},
    "EURUSD": {{
      "long_view": "長期方向",
      "long_reason": "根拠(50字)",
      "mid_view": "中期方向",
      "mid_reason": "根拠(50字)",
      "short_view": "短期方向",
      "short_reason": "根拠(50字)"
    }},
    "GBPUSD": {{
      "long_view": "長期方向",
      "long_reason": "根拠(50字)",
      "mid_view": "中期方向",
      "mid_reason": "根拠(50字)",
      "short_view": "短期方向",
      "short_reason": "根拠(50字)"
    }},
    "AUDUSD": {{
      "long_view": "長期方向",
      "long_reason": "根拠(50字)",
      "mid_view": "中期方向",
      "mid_reason": "根拠(50字)",
      "short_view": "短期方向",
      "short_reason": "根拠(50字)"
    }},
    "WTI": {{
      "long_view": "長期方向",
      "long_reason": "根拠(50字) ※原油需給・地政学・OPEC政策を考慮",
      "mid_view": "中期方向",
      "mid_reason": "根拠(50字)",
      "short_view": "短期方向",
      "short_reason": "根拠(50字)"
    }},
    "SP500": {{
      "long_view": "長期方向",
      "long_reason": "根拠(50字) ※FRB政策・企業業績・景気サイクルを考慮",
      "mid_view": "中期方向",
      "mid_reason": "根拠(50字)",
      "short_view": "短期方向",
      "short_reason": "根拠(50字)"
    }}
  }},
  "updated": "{today}"
}}"""

def get_outlook(data, retries=3):
    """Claude分析を取得。API一時エラーやJSON崩れに備えてリトライし、
    それでも失敗したら例外を投げずNoneを返す（呼び出し側で前回データを維持する）。"""
    client = anthropic.Anthropic()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                messages=[{"role": "user", "content": build_prompt(data)}]
            )
            raw = re.sub(r'```json|```', '', msg.content[0].text).strip()
            return json.loads(raw)
        except Exception as e:
            last_err = e
            print(f"  ⚠️ 分析取得失敗 (試行{attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(5 * attempt)
    print(f"  ❌ {retries}回試しても分析を取得できませんでした: {last_err}")
    return None

def main():
    print("\n" + "="*50)
    print(f"  FX Outlook v2  {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print("="*50)
    data = load_fundamental_data()
    if data is None:
        return
    print(f"  ニュース: {len(data.get('news',[]))}件 / COT: {len(data.get('cot',{}))}通貨")
    print("  Claude分析中...")
    outlook = get_outlook(data)
    if outlook is None:
        print("  ⚠️ 分析取得に失敗したため、既存のfx_outlook.jsonを維持して終了します（次回の自動更新で再試行されます）")
        return
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    with open(OUTLOOK_JSON, "w", encoding="utf-8") as f:
        json.dump(outlook, f, ensure_ascii=False, indent=2)
    print(f"  保存完了: {OUTLOOK_JSON}")
    print(f"\n  全体: {outlook.get('overall','')}")
    print(f"  リスク: {outlook.get('risk_mode','')} | {outlook.get('key_risk','')}")
    for bank, stance in outlook.get("cb_stance", {}).items():
        print(f"  {bank}: {stance}")
    for pair in TARGET_PAIRS:
        p = outlook.get("pairs", {}).get(pair, {})
        print(f"  {pair}: {p.get('long_view','')} / {p.get('mid_view','')} / {p.get('short_view','')}")

if __name__ == "__main__":
    main()
