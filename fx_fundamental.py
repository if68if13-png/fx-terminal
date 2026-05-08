#!/usr/bin/env python3
import requests, feedparser, datetime, os, json

SAVE_DIR = os.path.expanduser("~/Documents/FX分析")
os.makedirs(SAVE_DIR, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def get_news():
    sources = {
        "Fed": "https://www.federalreserve.gov/feeds/press_all.xml",
        "FXStreet": "https://www.fxstreet.com/rss/news",
        "DailyFX": "https://www.dailyfx.com/feeds/all",
        "Investing": "https://www.investing.com/rss/news_301.rss",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    }
    keywords = ["rate","inflation","employment","GDP","interest","FOMC","Fed","BOJ","ECB",
                "dollar","yen","euro","CPI","PMI","hawkish","dovish","hike","cut",
                "利上げ","利下げ","日銀","金利","為替","円安","円高"]
    items = []
    for name, url in sources.items():
        try:
            feed = feedparser.parse(url)
            count = 0
            for e in feed.entries[:10]:
                title = e.get("title","")
                summary = e.get("summary","")[:300]
                if any(k.lower() in (title+summary).lower() for k in keywords):
                    items.append({"source":name,"title":title,"summary":summary,"published":e.get("published","")})
                    count += 1
            if count > 0:
                print(f"  → {name}: {count}件")
        except Exception as ex:
            print(f"  ⚠️ {name}: {ex}")
    return items

def get_cot():
    try:
        r = requests.get("https://www.cftc.gov/dea/newcot/f_disagg.txt", headers=HEADERS, timeout=20)
        if r.status_code != 200: return {}
        targets = {"JAPANESE YEN":"JPY","EURO FX":"EUR","BRITISH POUND":"GBP","AUSTRALIAN DOLLAR":"AUD","CANADIAN DOLLAR":"CAD","SWISS FRANC":"CHF"}
        cot = {}
        for line in r.text.split("\n")[1:]:
            parts = line.split(",")
            if len(parts) < 10: continue
            name = parts[0].strip().strip('"').upper()
            for t, cur in targets.items():
                if t in name:
                    try:
                        long_p, short_p = int(parts[7].strip()), int(parts[8].strip())
                        net = long_p - short_p
                        cot[cur] = {"long":long_p,"short":short_p,"net":net,"bias":"🟢ロング優勢" if net>0 else "🔴ショート優勢"}
                    except: pass
        return cot
    except Exception as e:
        print(f"  ⚠️ COT: {e}")
        return {}

def score(news_items, cot):
    scores = {k:0 for k in ["USD","JPY","EUR","GBP","AUD","NZD","CAD","CHF"]}
    reasons = {k:[] for k in scores}
    for cur, data in cot.items():
        if abs(data.get("net",0)) > 50000:
            s = 1 if data["net"]>0 else -1
            scores[cur] += s
            reasons[cur].append(f"[COT] {data['bias']} (ネット:{data['net']:+,})")
    bullish = ["hawkish","rate hike","strong","beat","surge","タカ派","利上げ","強い","上昇","回復"]
    bearish = ["dovish","rate cut","weak","slowdown","miss","ハト派","利下げ","弱い","低下","後退","景気後退"]
    cwords = {
        "USD":["dollar","usd","fed ","fomc","powell","federal reserve"],
        "JPY":["yen","jpy","boj","日銀","円","ueda"],
        "EUR":["euro","eur","ecb","lagarde","eurozone"],
        "GBP":["pound","gbp","boe","bailey","sterling"],
        "AUD":["aussie","aud","rba","bullock"],
        "CAD":["cad","boc","loonie"],
        "CHF":["franc","chf","snb"],
        "NZD":["nzd","rbnz","kiwi"],
    }
    for item in news_items:
        text = (item.get("title","")+item.get("summary","")).lower()
        for cur, words in cwords.items():
            if any(w in text for w in words):
                b = sum(1 for w in bullish if w.lower() in text)
                s_c = sum(1 for w in bearish if w.lower() in text)
                if b > s_c:
                    scores[cur] = min(5, scores[cur]+1)
                    reasons[cur].append(f"[強気] {item['title'][:55]}")
                elif s_c > b:
                    scores[cur] = max(-5, scores[cur]-1)
                    reasons[cur].append(f"[弱気] {item['title'][:55]}")
    return scores, reasons

def judge(scores):
    pairs = [("USD","JPY","USDJPY"),("EUR","USD","EURUSD"),("GBP","USD","GBPUSD"),
             ("AUD","USD","AUDUSD"),("EUR","JPY","EURJPY"),("GBP","JPY","GBPJPY")]
    results = []
    for base, quote, pair in pairs:
        diff = scores.get(base,0) - scores.get(quote,0)
        if diff >= 3: d = "強くロング"
        elif diff >= 2: d = "ロング優勢"
        elif diff <= -3: d = "強くショート"
        elif diff <= -2: d = "ショート優勢"
        else: d = "様子見"
        results.append({"pair":pair,"direction":d,"diff":diff,"base_score":scores.get(base,0),"quote_score":scores.get(quote,0)})
    return sorted(results, key=lambda x: abs(x["diff"]), reverse=True)

def save_all(news_items, cot, scores, reasons, judgments):
    now = datetime.datetime.now()
    ts = now.strftime("%Y%m%d_%H%M")
    md = f"# FX分析レポート\n**生成:** {now.strftime('%Y年%m月%d日 %H:%M')}\n\n"
    md += "## 通貨強弱\n"
    for cur, s in sorted(scores.items(), key=lambda x: -x[1]):
        md += f"- {cur}: {'█'*abs(s)+'░'*(5-abs(s))} {s:+d}\n"
    md += "\n## ペア方向性\n"
    for j in judgments:
        md += f"- {j['pair']}: {j['direction']} (差:{j['diff']:+d})\n"
    md += "\n## ニュース\n"
    for n in news_items[:10]:
        md += f"- [{n['source']}] {n['title']}\n"
    for path in [f"{SAVE_DIR}/FX分析_{ts}.md", f"{SAVE_DIR}/FX分析_最新.md"]:
        with open(path,"w",encoding="utf-8") as f: f.write(md)
    json_data = {
        "timestamp": now.isoformat(),
        "generated": now.strftime("%Y年%m月%d日 %H:%M"),
        "scores": scores,
        "pairs": judgments,
        "news": [{"source":n.get("source",""),"title":n.get("title",""),"summary":n.get("summary","")[:120]} for n in news_items[:20]],
        "cot": cot,
        "reasons": {cur: lst for cur, lst in reasons.items() if lst},
    }
    with open(f"{SAVE_DIR}/fx_data.json","w",encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存完了")
    return f"{SAVE_DIR}/FX分析_{ts}.md"

def main():
    print("\n"+"="*50)
    print(f"  FX分析システム {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print("="*50)
    print("📰 ニュース取得中...")
    news_data = get_news()
    print(f"  合計: {len(news_data)}件")
    print("📋 COT取得中...")
    cot = get_cot()
    print(f"  → {len(cot)}通貨")
    print("🧮 スコアリング中...")
    scores, reasons = score(news_data, cot)
    judgments = judge(scores)
    print("💾 保存中...")
    path = save_all(news_data, cot, scores, reasons, judgments)
    print("\n"+"="*50)
    for cur, s in sorted(scores.items(), key=lambda x: -x[1]):
        print(f"  {cur}: {'█'*abs(s)+'░'*(5-abs(s))} {s:+d}")
    print()
    for j in judgments:
        emoji = "🟢" if "ロング" in j['direction'] else ("🔴" if "ショート" in j['direction'] else "⚪")
        print(f"  {j['pair']:8s} {emoji} {j['direction']}")
    print(f"\n✅ 完了: {path}")

if __name__ == "__main__":
    main()
