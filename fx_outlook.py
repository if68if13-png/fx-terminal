#!/usr/bin/env python3
import anthropic, json, datetime, os, re, time

ANALYSIS_DIR = os.environ.get("SAVE_DIR", os.path.dirname(os.path.abspath(__file__)))
FX_DATA_JSON = os.path.join(ANALYSIS_DIR, "fx_data.json")
OUTLOOK_JSON = os.path.join(ANALYSIS_DIR, "fx_outlook.json")
TARGET_PAIRS = ["USDJPY", "EURUSD"]

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

def format_technicals(technicals, pair):
    t = technicals.get(pair)
    if not t:
        return "データ取得できず（次回自動更新まで方向感の判断は保留してください）"
    parts = [f"現在値: {t.get('latest','—')}"]
    if t.get("sma20") is not None:
        parts.append(f"SMA20: {t['sma20']}（価格はSMA20の{t.get('vs_sma20','—')}）")
    if t.get("sma50") is not None:
        parts.append(f"SMA50: {t['sma50']}（価格はSMA50の{t.get('vs_sma50','—')}）")
    if t.get("sma200") is not None:
        parts.append(f"SMA200: {t['sma200']}（価格はSMA200の{t.get('vs_sma200','—')}）")
    if t.get("rsi14") is not None:
        parts.append(f"RSI(14): {t['rsi14']}")
    if t.get("low20") is not None:
        parts.append(f"直近20日レンジ: {t['low20']}〜{t['high20']}")
    if t.get("low60") is not None:
        parts.append(f"直近60日レンジ: {t['low60']}〜{t['high60']}")
    if t.get("chg5d_pct") is not None:
        parts.append(f"5日変化率: {t['chg5d_pct']:+.2f}%")
    if t.get("chg20d_pct") is not None:
        parts.append(f"20日変化率: {t['chg20d_pct']:+.2f}%")
    return " / ".join(parts)

def build_prompt(data):
    today = datetime.datetime.now().strftime("%Y年%m月%d日")
    news_text = "\n".join(f"- [{n.get('source','')}] {n.get('title','')} / {n.get('summary','')[:150]}" for n in data.get("news",[])[:20]) or "なし"
    cot_text = "\n".join(f"- {c}: net {d.get('net',0):+,} ({d.get('bias','')})" for c,d in data.get("cot",{}).items()) or "取得なし"
    scores = data.get("scores", {})
    score_text = "\n".join(f"- {c}: {s:+d}" for c,s in sorted(scores.items(), key=lambda x:-x[1]))
    admin = load_admin_data()
    fedwatch = admin.get("fedwatch", "")
    admin_text = f"FedWatch: {fedwatch}" if fedwatch else "（未入力）"
    rates = data.get("rates", {})
    rates_text = f"""- FF金利: {rates.get('US_FF','N/A')}%
- 米10年債: {rates.get('US_10Y','N/A')}%
- 日本10年債: {rates.get('JP_10Y','N/A')}%
- 独10年債: {rates.get('DE_10Y','N/A')}%
- USDJPY金利差(米-日): {rates.get('DIFF_USDJPY','N/A')}%
- EURUSD金利差(独-米): {rates.get('DIFF_EURUSD','N/A')}%"""
    technicals = data.get("technicals", {})
    usdjpy_tech = format_technicals(technicals, "USDJPY")
    eurusd_tech = format_technicals(technicals, "EURUSD")
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

【USD/JPY テクニカル指標】
{usdjpy_tech}

【EUR/USD テクニカル指標】
{eurusd_tech}

overall・risk_mode・key_risk・cb_stanceは、上記のニュース・COT・金利データなどファンダメンタルズ全般を踏まえて判断してください。

pairs（USDJPY, EURUSDの2つのみ）のlong_view/mid_view/short_viewとその根拠(reason)は、【テクニカル指標】のみを根拠にしてください。ニュースや金利差などのファンダメンタルズは考慮しないでください。目安として、長期(long)はSMA200との位置関係、中期(mid)はSMA50との位置関係と60日レンジ、短期(short)はSMA20・RSI(14)・直近20日レンジを中心に判断してください。reasonには根拠となった具体的な数値（SMA・RSIの値など）を必ず含めてください。

以下のJSON形式のみで返答。説明文・マークダウン不要:

{{
  "overall": "相場全体まとめ(40字以内)",
  "risk_mode": "リスクオン/リスクオフ/中立",
  "key_risk": "最重要リスクイベント(60字以内)",
  "cb_stance": {{
    "FRB": "タカ派/中立/ハト派+理由(30字)",
    "BOJ": "タカ派/中立/ハト派+理由(30字)",
    "ECB": "タカ派/中立/ハト派+理由(30字)"
  }},
  "pairs": {{
    "USDJPY": {{
      "long_view": "長期方向(テクニカル)",
      "long_reason": "根拠(50字、SMA200等の数値を含める)",
      "mid_view": "中期方向(テクニカル)",
      "mid_reason": "根拠(50字、SMA50等の数値を含める)",
      "short_view": "短期方向(テクニカル)",
      "short_reason": "根拠(50字、SMA20・RSI等の数値を含める)"
    }},
    "EURUSD": {{
      "long_view": "長期方向(テクニカル)",
      "long_reason": "根拠(50字、SMA200等の数値を含める)",
      "mid_view": "中期方向(テクニカル)",
      "mid_reason": "根拠(50字、SMA50等の数値を含める)",
      "short_view": "短期方向(テクニカル)",
      "short_reason": "根拠(50字、SMA20・RSI等の数値を含める)"
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
