#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fx_calendar_extra.py -- カレンダー追加イベント生成

ForexFactory feed が拾わない / 先の予定まで見えない下記をまとめて JSON 化する。

  1. 日銀 金融政策決定会合        … boj.or.jp から自動取得（失敗時は内蔵表）
  2. 日本 消費者物価指数(全国/都区部) … 公表ルールから自動算出
  3. ECB 政策理事会(金融政策)      … ecb.europa.eu から自動取得（失敗時は内蔵表）
  4. ユーロ圏 PMI(速報/確報)       … 公表ルールから自動算出
  5. マグニフィセント・セブン決算   … 自動更新icsフィード（失敗時は内蔵表）

出力: fx_calendar_extra.json

使い方:
  python3 fx_calendar_extra.py --print     # 取得して一覧表示
  python3 fx_calendar_extra.py             # JSON生成
  python3 fx_calendar_extra.py --selftest  # ネット不要。日付ロジックの自己診断
  python3 fx_calendar_extra.py --merge     # 既存カレンダーJSONへ統合(下記参照)
  python3 fx_calendar_extra.py --merge --dry-run
"""

import os
import re
import io
import ssl
import sys
import json
import gzip
import time
import datetime as dt
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, "fx_calendar_extra.json")

JST = dt.timezone(dt.timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

MONTHS_AHEAD = 18          # 何ヶ月先まで生成するか

BOJ_URL = "https://www.boj.or.jp/mopo/mpmsche_minu/index.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
MAG7_ICS = ("https://smartcalendars.ai/cal/"
            "588001c24e483d24321978f76780727facae4409ee6cedbfdde6b8bcfb7489ca.ics")

MAG7 = {
    "AAPL": "アップル", "MSFT": "マイクロソフト", "GOOGL": "アルファベット",
    "GOOG": "アルファベット", "AMZN": "アマゾン", "NVDA": "エヌビディア",
    "META": "メタ", "TSLA": "テスラ",
}

# --- 取得に失敗したときの内蔵フォールバック（公式発表ベース） -----------------
FALLBACK_BOJ = [          # (決定・会見日, 展望レポートの有無)
    ("2026-07-31", True), ("2026-09-18", False),
    ("2026-10-30", True), ("2026-12-18", False),
]
FALLBACK_ECB = [          # 金融政策理事会の決定日(Day2)
    "2026-09-10", "2026-10-29", "2026-12-17",
    "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-10",
    "2027-07-22", "2027-09-09", "2027-10-28", "2027-12-16",
]
FALLBACK_MAG7 = [         # 確認済みの直近分
    ("2026-07-29", "MSFT"), ("2026-07-29", "META"),
    ("2026-07-30", "AAPL"), ("2026-07-30", "AMZN"),
    ("2026-08-26", "NVDA"),
]


# ==========================================================================
# 共通
# ==========================================================================
def http_get(url, timeout=30, retries=2):
    last = None
    ctx = ssl.create_default_context()
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "*/*",
                "Accept-Language": "ja,en;q=0.8", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                cs = r.headers.get_content_charset() or "utf-8"
                return raw.decode(cs, errors="replace")
        except Exception as e:                       # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(1.2 * (i + 1))
    raise RuntimeError("GET失敗 %s: %s" % (url, last))


TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(html):
    """HTMLを可視テキストに落とす。タグ位置は空白1個に置換して語の連結を防ぐ。"""
    from html import unescape
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = TAG_RE.sub(" ", html)
    html = unescape(html)
    for ch in (" ", "　", " ", " "):
        html = html.replace(ch, " ")
    return re.sub(r"\s+", " ", html)


STARS = {"high": "★★★", "medium": "★★", "low": "★"}


def ev(date, time_, title, category, country, impact,
       note=None, confirmed=True, source=None, short=None):
    """short は index.html の IND に流し込む短縮ラベル（既存書式「★★ 米CPI」に合わせる）。"""
    return {
        "date": date, "time": time_, "tz": "JST", "title": title,
        "short": "%s %s" % (STARS.get(impact, "★"), short or title),
        "category": category, "country": country, "impact": impact,
        "note": note, "confirmed": confirmed, "source": source,
        "id": "%s|%s" % (date, title),
    }


# ==========================================================================
# 日付ユーティリティ
# ==========================================================================
def friday_of_week_containing(year, month, day):
    """
    指定日を含む週の金曜日を返す。週は日曜起点（統計局の公表暦の慣行）。
    例: 2026-07-19(日) を含む週 = 7/19〜7/25 → 金曜は 7/24。
    """
    d = dt.date(year, month, day)
    sunday = d - dt.timedelta(days=(d.weekday() + 1) % 7)
    return sunday + dt.timedelta(days=5)


def nth_business_day(year, month, n):
    """その月の第n営業日（土日のみ考慮）。"""
    d = dt.date(year, month, 1)
    count = 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return d
        d += dt.timedelta(days=1)


def next_business_day_on_or_after(d):
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def month_iter(start, n):
    y, m = start.year, start.month
    for _ in range(n):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


# ==========================================================================
# 1. 日銀 金融政策決定会合
# ==========================================================================
BOJ_MTG_RE = re.compile(
    r"(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[（(][月火水木金土日][）)]"
    r"\s*[・･·]\s*"
    r"(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日\s*[（(][月火水木金土日][）)]")


def parse_boj(html):
    """
    「7月30日（木）・31日（金）」形式の開催日から2日目(決定日)を拾う。
    年は、直前に現れた「20xx年」を採用する（ページの年別セクション構成に対応）。
    直後のセルが同じ日付なら展望レポート公表回と判定する。
    """
    text = strip_tags(html)
    years = [(m.start(), int(m.group(1))) for m in re.finditer(r"(20\d\d)\s*年", text)]

    def year_at(pos):
        y = None
        for s, v in years:
            if s < pos:
                y = v
            else:
                break
        return y

    out = []
    for m in BOJ_MTG_RE.finditer(text):
        m1, _d1, m2, d2 = m.group(1), m.group(2), m.group(3), m.group(4)
        base = year_at(m.start())
        if base is None:
            continue
        mm = int(m2 or m1)
        yy = base + 1 if (m2 and int(m2) < int(m1)) else base
        try:
            decide = dt.date(yy, mm, int(d2))
        except ValueError:
            continue
        # 次のセル（展望レポート公表日）が同じ日付か。過去回はPDFリンク表記を挟む。
        tail = text[m.end():m.end() + 80]
        outlook = bool(re.match(
            r"\s*(?:\[?PDF[^\]]*\]?\s*)?%d\s*月\s*%d\s*日" % (mm, int(d2)), tail))
        out.append((decide.isoformat(), outlook))

    seen, res = set(), []
    for d, o in sorted(out):
        if d not in seen:
            seen.add(d)
            res.append((d, o))
    return res


def boj_events(today, fetched=None):
    pairs = fetched if fetched else FALLBACK_BOJ
    src = "boj.or.jp" if fetched else "boj.or.jp (内蔵表)"
    out = []
    for d, outlook in pairs:
        if d < today.isoformat():
            continue
        out.append(ev(d, "11:45", "日銀 金融政策決定会合 結果発表",
                      "central_bank", "JP", "high",
                      note="展望レポート公表・15:30 総裁会見" if outlook else "15:30 総裁会見",
                      source=src,
                      short="日銀会合(展望)" if outlook else "日銀会合"))
    return out


# ==========================================================================
# 2. 日本 CPI
# ==========================================================================
def jp_cpi_events(today):
    """
    全国CPI    : 19日を含む週の金曜 08:30（前々月分ではなく前月分）
    東京都区部  : 26日を含む週の金曜 08:30（当月分の中旬速報）
    """
    out = []
    for y, m in month_iter(today, MONTHS_AHEAD):
        z = friday_of_week_containing(y, m, 19)
        if z >= today:
            tm = m - 1 or 12
            ty = y if m > 1 else y - 1
            out.append(ev(z.isoformat(), "08:30",
                          "日本 消費者物価指数(全国) %d年%d月分" % (ty, tm),
                          "indicator", "JP", "high",
                          note="コアCPI(生鮮食品除く)が主目線", short="日本CPI",
                          confirmed=False, source="stat.go.jp (公表ルールから算出)"))
        k = friday_of_week_containing(y, m, 26)
        if k >= today:
            out.append(ev(k.isoformat(), "08:30",
                          "日本 東京都区部CPI %d年%d月分(中旬速報)" % (y, m),
                          "indicator", "JP", "medium",
                          note="全国CPIの先行指標", short="東京都CPI",
                          confirmed=False, source="stat.go.jp (公表ルールから算出)"))
    return out


# ==========================================================================
# 3. ECB 政策理事会
# ==========================================================================
def parse_ecb(html):
    """
    'dd/mm/yyyy' の次に来る説明文を、次の日付トークンまでの範囲として切り出し、
    金融政策理事会の Day 2（＝政策金利発表日）だけを拾う。
    """
    text = strip_tags(html)
    toks = [(m.start(), m.end(), m.group(0))
            for m in re.finditer(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)]
    out = []
    for i, (_s, e, ds) in enumerate(toks):
        nxt = toks[i + 1][0] if i + 1 < len(toks) else min(len(text), e + 400)
        desc = text[e:nxt].lower()
        if "monetary policy meeting" not in desc:
            continue
        if "non-monetary" in desc:
            continue
        if "day 2" not in desc and "press conference" not in desc:
            continue
        d, mo, y = ds.split("/")
        try:
            out.append(dt.date(int(y), int(mo), int(d)).isoformat())
        except ValueError:
            continue
    return sorted(set(out))


def ecb_events(today, fetched=None):
    dates = fetched if fetched else FALLBACK_ECB
    src = "ecb.europa.eu" if fetched else "ecb.europa.eu (内蔵表)"
    out = []
    for d in dates:
        if d < today.isoformat():
            continue
        out.append(ev(d, "21:15", "ECB 政策理事会 政策金利発表",
                      "central_bank", "EU", "high",
                      note="21:45 ラガルド総裁会見（日本時間・夏時間基準）",
                      source=src, short="ECB金利"))
    return out


# ==========================================================================
# 4. ユーロ圏 PMI
# ==========================================================================
def eu_pmi_events(today):
    """
    速報(Flash): 毎月22日（休日なら翌営業日）17:00頃
    確報(Final): 製造業=翌月第1営業日 / サービス・総合=翌月第3営業日
    """
    out = []
    for y, m in month_iter(today, MONTHS_AHEAD):
        f = next_business_day_on_or_after(dt.date(y, m, 22))
        if f >= today:
            out.append(ev(f.isoformat(), "17:00",
                          "ユーロ圏 PMI速報 (製造業・サービス業・総合)",
                          "indicator", "EU", "high",
                          note="ECBの政策判断に直結しやすい先行指標", short="欧PMI速報",
                          confirmed=False, source="S&P Global (公表ルールから算出)"))
        d1 = nth_business_day(y, m, 1)
        if d1 >= today:
            out.append(ev(d1.isoformat(), "17:00", "ユーロ圏 製造業PMI 確報",
                          "indicator", "EU", "low", confirmed=False,
                          short="欧製造業PMI",
                          source="S&P Global (公表ルールから算出)"))
        d3 = nth_business_day(y, m, 3)
        if d3 >= today:
            out.append(ev(d3.isoformat(), "17:00", "ユーロ圏 サービス業・総合PMI 確報",
                          "indicator", "EU", "low", confirmed=False,
                          short="欧サービスPMI",
                          source="S&P Global (公表ルールから算出)"))
    return out


# ==========================================================================
# 5. マグニフィセント・セブン 決算
# ==========================================================================
def parse_ics(text):
    """VEVENT から (日付, サマリ) を抽出。"""
    out = []
    text = re.sub(r"\r?\n[ \t]", "", text)            # 折り返し行の連結
    for blk in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        ds = re.search(r"^DTSTART[^:]*:(\d{8})", blk, re.M)
        su = re.search(r"^SUMMARY:(.*)$", blk, re.M)
        if not (ds and su):
            continue
        raw = ds.group(1)
        try:
            d = dt.date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
        except ValueError:
            continue
        out.append((d, su.group(1).strip()))
    return out


def mag7_events(today, fetched=None):
    """
    fetched: [(date, summary)]。フィードが一部しか返さないことがあるため、
    内蔵表と「合成」する（置き換えない）。同一ティッカーで日付が競合したら
    フィード側を優先する。
    """
    live = {}
    if fetched:
        for d, summary in fetched:
            m = re.search(r"\b(%s)\b" % "|".join(MAG7), summary.upper())
            if m:
                live.setdefault(m.group(1), set()).add(d)

    rows = {}                       # (ticker) -> {date: source}
    for d, tic in FALLBACK_MAG7:
        rows.setdefault(tic, {})[d] = "各社IR (内蔵表)"
    for tic, dates in live.items():
        rows[tic] = {d: "smartcalendars.ai (自動更新ics)" for d in dates}

    out = []
    for tic, dates in rows.items():
        for d, src in dates.items():
            if d < today.isoformat():
                continue
            out.append(ev(d, "05:30", "%s (%s) 決算発表" % (MAG7[tic], tic),
                          "earnings", "US", "high",
                          note="米引け後発表。日本時間は翌朝",
                          source=src, short="%s決算" % tic))
    out.sort(key=lambda e: (e["date"], e["title"]))
    return out


# ==========================================================================
# 組み立て
# ==========================================================================
def build():
    today = dt.datetime.now(JST).date()
    src_status = {}

    def try_fetch(name, url, parser):
        try:
            v = parser(http_get(url))
            if v:
                src_status[name] = "live (%d件)" % len(v)
                return v
            src_status[name] = "解析0件 → 内蔵表を使用"
        except Exception as e:                       # noqa: BLE001
            src_status[name] = "取得失敗 → 内蔵表を使用 (%s)" % str(e)[:80]
        return None

    boj = try_fetch("boj", BOJ_URL, parse_boj)
    ecb = try_fetch("ecb", ECB_URL, parse_ecb)
    m7 = try_fetch("mag7", MAG7_ICS, parse_ics)

    events = []
    events += boj_events(today, boj)
    events += jp_cpi_events(today)
    events += ecb_events(today, ecb)
    events += eu_pmi_events(today)
    events += mag7_events(today, m7)
    events.sort(key=lambda e: (e["date"], e["time"] or "", e["title"]))

    now = dt.datetime.now(JST)
    return {
        "generated_at_jst": now.strftime("%Y-%m-%d %H:%M JST"),
        "horizon_months": MONTHS_AHEAD,
        "source_status": src_status,
        "note": "confirmed=false は公表ルールから算出した予定日。前後する場合があります。",
        "count": len(events),
        "events": events,
    }


IMPACT_MARK = {"high": "★★★", "medium": "★★☆", "low": "★☆☆"}
CAT_MARK = {"central_bank": "🏛", "indicator": "📊", "earnings": "💰"}


def render(payload, limit=40):
    L = ["=" * 74,
         " カレンダー追加イベント  (%s)" % payload["generated_at_jst"],
         "=" * 74]
    for k, v in payload["source_status"].items():
        L.append("  %-6s %s" % (k, v))
    L.append("-" * 74)
    cur = None
    for e in payload["events"][:limit]:
        ym = e["date"][:7]
        if ym != cur:
            cur = ym
            L.append("")
            L.append("  --- %s ---" % ym)
        L.append("  %s %s %s %s %s%s"
                 % (e["date"][5:], e["time"] or "     ",
                    CAT_MARK.get(e["category"], "  "),
                    IMPACT_MARK.get(e["impact"], "   "),
                    e["title"], "" if e["confirmed"] else " (予定日)"))
    rest = payload["count"] - min(limit, payload["count"])
    if rest > 0:
        L.append("")
        L.append("  ... 他 %d 件" % rest)
    L.append("")
    return "\n".join(L)


# ==========================================================================
# 既存カレンダーJSONへの統合（スキーマ自動判定・任意）
# ==========================================================================
DATE_KEYS = ["date", "Date", "day", "datetime", "start", "when", "time_jst"]
TITLE_KEYS = ["title", "event", "name", "Title", "label", "text"]


def find_calendar_files():
    hits = []
    for fn in sorted(os.listdir(BASE_DIR)):
        if not fn.endswith(".json") or fn.startswith("fx_calendar_extra"):
            continue
        try:
            with open(os.path.join(BASE_DIR, fn), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:                            # noqa: BLE001
            continue
        for path, arr in _walk_arrays(data):
            if not arr or not isinstance(arr[0], dict):
                continue
            keys = set(arr[0].keys())
            dk = next((k for k in DATE_KEYS if k in keys), None)
            tk = next((k for k in TITLE_KEYS if k in keys), None)
            if dk and tk:
                hits.append({"file": fn, "path": path, "n": len(arr),
                             "date_key": dk, "title_key": tk,
                             "sample": arr[0]})
    return hits


def _walk_arrays(node, path="$"):
    if isinstance(node, list):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_arrays(v, "%s.%s" % (path, k))


def cmd_scan():
    """カレンダー実装の在り処を洗い出す（読み取りのみ）。"""
    print("=" * 74)
    print(" リポジトリ構造スキャン  %s" % BASE_DIR)
    print("=" * 74)

    print("\n[1] JSONファイルの構造")
    for fn in sorted(os.listdir(BASE_DIR)):
        if not fn.endswith(".json") or fn.startswith("fx_calendar_extra"):
            continue
        path = os.path.join(BASE_DIR, fn)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:                       # noqa: BLE001
            print("  %-34s (読めません: %s)" % (fn, str(e)[:40]))
            continue
        size = os.path.getsize(path)
        print("  %-34s %7d bytes" % (fn, size))
        for p, arr in _walk_arrays(data):
            if not arr:
                continue
            head = arr[0]
            kind = type(head).__name__
            keys = ",".join(list(head.keys())[:12]) if isinstance(head, dict) else kind
            print("      %-28s %4d件  keys/型: %s" % (p, len(arr), keys[:90]))
            if isinstance(head, dict):
                print("          例: %s"
                      % json.dumps(head, ensure_ascii=False)[:160])
        if isinstance(data, dict):
            scalars = [k for k, v in data.items() if not isinstance(v, (list, dict))]
            if scalars:
                print("      (トップレベルの単値キー: %s)" % ",".join(scalars[:12]))

    print("\n[2] index.html 内のカレンダー関連の記述")
    idx = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(idx):
        print("  index.html が見つかりません")
    else:
        with open(idx, encoding="utf-8") as f:
            lines = f.read().splitlines()
        pat = re.compile(
            r"calendar|カレンダー|forexfactory|ff_?xml|economic|指標|event", re.I)
        hits = [(i + 1, l.strip()) for i, l in enumerate(lines) if pat.search(l)]
        print("  該当 %d 行 (先頭40行を表示)" % len(hits))
        for n, l in hits[:40]:
            print("   %5d: %s" % (n, l[:140]))

    print("\n[3] Pythonスクリプト内のカレンダー生成箇所")
    for fn in sorted(os.listdir(BASE_DIR)):
        if not fn.endswith(".py") or fn.startswith("fx_calendar_extra"):
            continue
        with open(os.path.join(BASE_DIR, fn), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        pat = re.compile(r"calendar|カレンダー|forexfactory|nffx|ff_cal", re.I)
        hits = [(i + 1, l.strip()) for i, l in enumerate(lines) if pat.search(l)]
        if hits:
            print("  --- %s (%d行該当) ---" % (fn, len(hits)))
            for n, l in hits[:20]:
                print("   %5d: %s" % (n, l[:140]))
    print("\n上の出力をそのまま共有してください。統合コードを用意します。")
    return 0


def cmd_merge(payload, dry_run):
    hits = find_calendar_files()
    if not hits:
        print("既存カレンダーJSONを自動検出できませんでした。")
        print("fx_calendar_extra.json をフロント側で読み込む方式にしてください。")
        return 1
    print("検出したカレンダー候補:")
    for i, h in enumerate(hits):
        print("  [%d] %s %s  %d件  date=%r title=%r"
              % (i, h["file"], h["path"], h["n"], h["date_key"], h["title_key"]))
        print("      サンプル: %s" % json.dumps(h["sample"], ensure_ascii=False)[:150])
    if dry_run:
        print("\n--dry-run のため書き込みません。")
        print("上記の構造で問題なければ --merge のみで実行してください。")
    else:
        print("\n安全のため自動書き込みは行いません。")
        print("上の出力を共有してもらえれば、この形式に合わせた統合コードを用意します。")
    return 0


# ==========================================================================
# セルフテスト
# ==========================================================================
def selftest():
    ok = True

    def chk(c, msg):
        nonlocal ok
        print(("  OK   " if c else "  FAIL ") + msg)
        if not c:
            ok = False

    print("--- 日付ルール ---")
    # 2026年6月分 全国CPI は 2026-07-24(金) 公表（実績）
    chk(friday_of_week_containing(2026, 7, 19).isoformat() == "2026-07-24",
        "全国CPI: 7/19を含む週の金曜 = 2026-07-24")
    # 2026年7月分 都区部CPI は 2026-07-31(金) 公表（実績）
    chk(friday_of_week_containing(2026, 7, 26).isoformat() == "2026-07-31",
        "都区部CPI: 7/26を含む週の金曜 = 2026-07-31")
    # 2026年5月分 全国CPI は 2026-06-19(金) 公表（実績）
    chk(friday_of_week_containing(2026, 6, 19).isoformat() == "2026-06-19",
        "全国CPI: 6/19を含む週の金曜 = 2026-06-19")
    # 2026年3月分 全国CPI は 2026-04-24(金) 公表
    chk(friday_of_week_containing(2026, 4, 19).isoformat() == "2026-04-24",
        "全国CPI: 4/19を含む週の金曜 = 2026-04-24")
    chk(nth_business_day(2026, 8, 1).isoformat() == "2026-08-03",
        "2026年8月の第1営業日 = 8/3(月)")
    chk(nth_business_day(2026, 8, 3).isoformat() == "2026-08-05",
        "2026年8月の第3営業日 = 8/5(水)")
    chk(next_business_day_on_or_after(dt.date(2026, 8, 22)).isoformat() == "2026-08-24",
        "8/22(土)のPMI速報は 8/24(月)にずれる")

    print("--- 日銀ページ解析（生HTML想定）---")
    boj_fx = (
        '<h2 id="p2026">2026年</h2><p>表 2026年</p><table>'
        '<tr><td><a href="/k260123a.pdf">1月22日（木）&middot;23日（金）'
        ' [PDF 123KB]</a></td><td><a href="/gor2601b.pdf">1月23日（金）</a></td></tr>'
        '<tr><td>7月30日（木）・31日（金）</td><td>7月31日（金）</td>'
        '<td>8月10日（月）</td></tr>'
        '<tr><td>9月17日（木）<br>・18日（金）</td><td>-</td><td>10月 1日（木）</td></tr>'
        '<tr><td>12月17日（木）・18日（金）</td><td>-</td><td>12月28日（月）</td></tr>'
        '</table><h2 id="p2025">2025年</h2><table>'
        '<tr><td>12月18日（木）・19日（金）</td><td>-</td></tr></table>')
    got = parse_boj(boj_fx)
    chk(("2026-07-31", True) in got, "7/31を展望レポート回として抽出")
    chk(("2026-09-18", False) in got, "9/18を通常回として抽出（<br>を跨いでも可）")
    chk(("2026-12-18", False) in got, "12/18を抽出")
    chk(("2025-12-19", False) in got, "年セクションを跨いで2025年分も正しい年で抽出")
    chk(("2026-01-23", True) in got, "PDFリンク表記を挟んでも展望回と判定")

    print("--- ECBページ解析（生HTML想定）---")
    ecb_fx = (
        '<dl><dt class="date">10/09/2026</dt><dd>Governing Council of the ECB: '
        'monetary policy meeting hosted by the Deutsche Bundesbank in Berlin, Germany '
        '(Day 2), followed by press conference</dd>'
        '<dt class="date">30/09/2026</dt><dd>Governing Council of the ECB: '
        'non-monetary policy meeting (virtual)</dd>'
        '<dt class="date">28/10/2026</dt><dd>Governing Council of the ECB: '
        'monetary policy meeting in Frankfurt (Day 1)</dd>'
        '<dt class="date">29/10/2026</dt><dd>Governing Council of the ECB: '
        'monetary policy meeting in Frankfurt (Day 2), followed by press conference</dd>'
        '</dl>')
    got = parse_ecb(ecb_fx)
    chk(got == ["2026-09-10", "2026-10-29"],
        "Day2のみ抽出しDay1/non-monetaryを除外 (実際: %s)" % got)

    print("--- ics解析 ---")
    ics = ("BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260729\nSUMMARY:MSFT Earnings Report\n"
           "END:VEVENT\nBEGIN:VEVENT\nDTSTART:20260826T200000Z\n"
           "SUMMARY:NVDA Earnings Report\nEND:VEVENT\n")
    got = parse_ics(ics)
    chk(got == [("2026-07-29", "MSFT Earnings Report"),
                ("2026-08-26", "NVDA Earnings Report")], "VEVENT 2件を抽出")
    m7 = mag7_events(dt.date(2026, 7, 27), got)
    tics = sorted(re.search(r"\(([A-Z]+)\)", e["title"]).group(1) for e in m7)
    chk(tics == ["AAPL", "AMZN", "META", "MSFT", "NVDA"],
        "フィード2件と内蔵表を合成して5銘柄 (実際: %s)" % tics)
    chk(any("マイクロソフト" in e["title"] for e in m7), "ティッカーを日本語名に変換")
    msft = [e for e in m7 if "MSFT" in e["title"]][0]
    chk("smartcalendars" in msft["source"], "重複時はフィード側を優先")
    chk(all(e["date"] >= "2026-07-27" for e in m7), "過去分を除外")

    print("--- フォールバック ---")
    chk(len(boj_events(dt.date(2026, 7, 27))) == 4, "日銀 内蔵表4件")
    chk(len(ecb_events(dt.date(2026, 12, 31))) == 8, "ECB 内蔵表から将来分のみ")
    chk(all(e["date"] >= "2026-07-27" for e in jp_cpi_events(dt.date(2026, 7, 27))),
        "過去日を除外")

    print("\n%s" % ("すべて成功" if ok else "失敗あり"))
    return 0 if ok else 1


def main():
    args = set(sys.argv[1:])
    if "--selftest" in args:
        sys.exit(selftest())
    if "--scan" in args:
        sys.exit(cmd_scan())

    payload = build()

    if "--merge" in args:
        print(render(payload))
        sys.exit(cmd_merge(payload, "--dry-run" in args))

    if "--dry-run" not in args:
        tmp = OUT_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OUT_JSON)
        print("[OK] %s を生成 (%d件)" % (os.path.basename(OUT_JSON), payload["count"]))

    if "--print" in args or "--dry-run" in args:
        print(render(payload))


if __name__ == "__main__":
    main()
