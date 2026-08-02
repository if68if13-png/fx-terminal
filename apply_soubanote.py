#!/usr/bin/env python3
"""
FX Terminal - 「相場ノート」機能 追加パッチ
~/Documents/FX分析/ で実行してください（fx-terminal リポジトリのルート）。

やること:
  1. fx_fundamental.py の get_prices() を USD/JPY 専用に変更し、
     main() で呼び出すよう復活（始値・現在値(終値相当)・前日終値を取得）
  2. index.html に「📝 相場ノート」タブを追加
     - 上部にドル円の本日始値・終値(現在値)を自動表示
     - アプリから直接テキストを書いて保存（GitHub Contents APIで直接コミット）
     - 過去のノート一覧を閲覧可能
  3. fx_notes.json を新規作成（空配列）

実行前に各ファイルの .bak バックアップを作成し、
置換後は assert で検証してから書き込みます。
"""
import os, shutil, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def backup(path):
    if os.path.exists(path):
        shutil.copy(path, path + ".bak")
        print(f"  📦 バックアップ: {path}.bak")

def patch_fx_fundamental():
    path = os.path.join(BASE, "fx_fundamental.py")
    src = open(path, encoding="utf-8").read()

    old_func = '''def get_prices():
    """Twelve DataAPIから前日始値・当日始値を取得"""
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not api_key:
        print("  ⚠️ TWELVE_DATA_API_KEY未設定")
        return {}

    symbols = {
        "USDJPY": "USD/JPY",
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "AUDUSD": "AUD/USD",
        "WTI":    "USO",
        "SP500":  "SPY",
    }

    prices = {}
    import requests
    for key, symbol in symbols.items():
        try:
            r = requests.get("https://api.twelvedata.com/time_series", params={
                "symbol":     symbol,
                "interval":   "1day",
                "outputsize": 2,
                "apikey":     api_key,
            }, timeout=10)
            d = r.json()
            vals = d.get("values", [])
            if len(vals) >= 2:
                today_open = float(vals[0]["open"])
                prev_open  = float(vals[1]["open"])
                diff = round(today_open - prev_open, 4)
                diff_pct = round((diff / prev_open) * 100, 2)
                prices[key] = {
                    "today_open": today_open,
                    "prev_open":  prev_open,
                    "diff":       diff,
                    "diff_pct":   diff_pct,
                }
                print(f"  {key}: 前日始値{prev_open} → 当日始値{today_open} ({diff_pct:+.2f}%)")
        except Exception as e:
            print(f"  ⚠️ {key} 価格取得失敗: {e}")
    return prices'''

    new_func = '''def get_prices():
    """Twelve Data APIからUSD/JPYの本日始値・現在値(終値相当)・前日終値を取得
    相場ノート機能で使用。API消費を抑えるためUSD/JPYのみ取得。"""
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not api_key:
        print("  ⚠️ TWELVE_DATA_API_KEY未設定")
        return {}

    prices = {}
    import requests
    try:
        r = requests.get("https://api.twelvedata.com/time_series", params={
            "symbol":     "USD/JPY",
            "interval":   "1day",
            "outputsize": 2,
            "apikey":     api_key,
        }, timeout=10)
        d = r.json()
        vals = d.get("values", [])
        if len(vals) >= 1:
            today_open  = float(vals[0]["open"])
            today_close = float(vals[0]["close"])
            prev_close  = float(vals[1]["close"]) if len(vals) >= 2 else None
            diff     = round(today_close - prev_close, 4) if prev_close is not None else None
            diff_pct = round((diff / prev_close) * 100, 2) if diff is not None and prev_close else None
            prices["USDJPY"] = {
                "today_open":  today_open,
                "today_close": today_close,
                "prev_close":  prev_close,
                "diff":        diff,
                "diff_pct":    diff_pct,
            }
            msg = f"  USDJPY: 始値{today_open} 現在値{today_close}"
            if diff_pct is not None:
                msg += f" (前日比 {diff_pct:+.2f}%)"
            print(msg)
    except Exception as e:
        print(f"  ⚠️ USDJPY価格取得失敗: {e}")
    return prices'''

    assert old_func in src, "❌ get_prices() の元コードが見つかりません（手動確認が必要です）"
    src = src.replace(old_func, new_func)

    old_main = '''    print("💾 保存中...")
    prices = {}
    path = save_all(news_data, cot, scores, reasons, judgments, rates, prices)'''
    new_main = '''    print("💹 USD/JPY価格取得中...")
    prices = get_prices()
    print("💾 保存中...")
    path = save_all(news_data, cot, scores, reasons, judgments, rates, prices)'''
    assert old_main in src, "❌ main() の元コードが見つかりません（手動確認が必要です）"
    src = src.replace(old_main, new_main)

    backup(path)
    open(path, "w", encoding="utf-8").write(src)
    import ast
    ast.parse(src)  # シンタックス検証
    print("✅ fx_fundamental.py 更新完了")


def patch_index_html():
    path = os.path.join(BASE, "index.html")
    src = open(path, encoding="utf-8").read()

    old_tabs = '''  <div class="tab" data-panel="p6" onclick="showTab('p6')">🗓 カレンダー</div>
  <div class="tab hidden-tab" data-panel="p1" onclick="showTab('p1')">🔍 分析</div>'''
    new_tabs = '''  <div class="tab" data-panel="p6" onclick="showTab('p6')">🗓 カレンダー</div>
  <div class="tab" data-panel="p7" onclick="showTab('p7')">📝 相場ノート</div>
  <div class="tab hidden-tab" data-panel="p1" onclick="showTab('p1')">🔍 分析</div>'''
    assert old_tabs in src, "❌ タブ挿入位置が見つかりません（手動確認が必要です）"
    src = src.replace(old_tabs, new_tabs)

    old_anchor = '''<div class="refresh-bar">'''
    new_panel = '''<div class="panel" id="p7">
  <div class="comment-card" id="note-price-card">
    <div class="comment-label">USD/JPY 本日</div>
    <div id="note-price-bar" style="font-size:.85rem;color:#c9d1d9">読込中...</div>
  </div>

  <div class="comment-card">
    <div class="comment-label">相場ノート</div>
    <textarea id="note-textarea" rows="6" placeholder="今日の相場感、トレード、気づきなどを自由に記録..." style="width:100%;background:#0d1117;border:1px solid #1a2332;border-radius:6px;color:#c9d1d9;padding:12px;font-size:.85rem;line-height:1.6;resize:vertical;font-family:inherit"></textarea>
    <button class="refresh-btn" style="margin-top:10px;width:100%" onclick="saveNote()">💾 保存</button>
    <div id="note-save-msg" style="font-size:.7rem;color:#00ff88;margin-top:6px;display:none">✅ 保存しました</div>
    <div id="note-token-hint" style="font-size:.68rem;color:#4a5568;margin-top:8px;display:none">
      初回のみ：<a href="#" onclick="setupNoteToken();return false;" style="color:#00d4ff">GitHubトークンを設定</a>
    </div>
  </div>

  <span class="slabel" style="margin-top:14px">📖 過去のノート</span>
  <div id="note-history-list"><div style="color:#4a5568;font-size:.8rem">読込中...</div></div>
</div>

<div class="refresh-bar">'''
    assert old_anchor in src, "❌ パネル挿入位置が見つかりません（手動確認が必要です）"
    src = src.replace(old_anchor, new_panel, 1)

    old_fetchall = '''    const d1=await r1.json();
    const outlook=r2.ok?await r2.json():{};
    const d2=r3&&r3.ok?await r3.json():{};
    renderScores(d1);renderCot(d1);renderNews(d1);renderReasons(d1);renderAdmin(d2);renderOutlook(outlook);renderPairs(outlook,d1);renderEurUsdHorizon(outlook);renderRates(d1);
    s.textContent='✅ '+d1.generated;'''
    new_fetchall = '''    const d1=await r1.json();
    window.FXDATA=d1;
    const outlook=r2.ok?await r2.json():{};
    const d2=r3&&r3.ok?await r3.json():{};
    renderScores(d1);renderCot(d1);renderNews(d1);renderReasons(d1);renderAdmin(d2);renderOutlook(outlook);renderPairs(outlook,d1);renderEurUsdHorizon(outlook);renderRates(d1);renderNotePriceBar(d1);
    s.textContent='✅ '+d1.generated;'''
    assert old_fetchall in src, "❌ fetchAll() の該当箇所が見つかりません（手動確認が必要です）"
    src = src.replace(old_fetchall, new_fetchall)

    old_listeners = '''window.addEventListener('load',fetchAll);
window.addEventListener('load',fetchMarkets);
window.addEventListener('load',fetchHistory);
setInterval(fetchAll,30*60*1000);'''

    note_js = '''// ── 相場ノート ──
const GH_OWNER='if68if13-png';
const GH_REPO='fx-terminal';
const GH_BRANCH='main';
const NOTES_PATH='fx_notes.json';
let notesCache=[];
let notesSha=null;

function todayStr(){
  const d=new Date();
  const jst=new Date(d.getTime()+(d.getTimezoneOffset()+9*60)*60000);
  return jst.toISOString().slice(0,10);
}
function getGhToken(){ return localStorage.getItem('fx_gh_token')||''; }
function setGhToken(t){ localStorage.setItem('fx_gh_token', t); }
function setupNoteToken(){
  const cur=getGhToken();
  const t=prompt('GitHubトークン（if68if13-png/fx-terminal リポジトリのContents書込権限を持つFine-grained PAT）を入力してください。\\nこの端末のブラウザ内(localStorage)にのみ保存され、他には送信されません。', cur||'');
  if(t!==null && t.trim()){
    setGhToken(t.trim());
    document.getElementById('note-token-hint').style.display='none';
  }
}
function b64EncodeUtf8(str){ return btoa(unescape(encodeURIComponent(str))); }
function b64DecodeUtf8(b64){ return decodeURIComponent(escape(atob(b64.replace(/\\n/g,'')))); }

async function ghGetFile(path){
  const token=getGhToken();
  const headers={Accept:'application/vnd.github+json'};
  if(token) headers.Authorization='Bearer '+token;
  const res=await fetch(`https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${path}?ref=${GH_BRANCH}`,{headers});
  if(res.status===404) return {sha:null,data:[]};
  if(!res.ok) throw new Error('GitHub読込エラー: '+res.status);
  const j=await res.json();
  return {sha:j.sha, data: JSON.parse(b64DecodeUtf8(j.content))};
}
async function ghPutFile(path,dataObj,sha,message){
  const token=getGhToken();
  if(!token) throw new Error('NO_TOKEN');
  const body={message, content:b64EncodeUtf8(JSON.stringify(dataObj,null,2)), branch:GH_BRANCH};
  if(sha) body.sha=sha;
  const res=await fetch(`https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${path}`,{
    method:'PUT',
    headers:{Authorization:'Bearer '+token, Accept:'application/vnd.github+json', 'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if(!res.ok){
    const err=await res.json().catch(()=>({}));
    throw new Error('GitHub保存エラー: '+res.status+' '+(err.message||''));
  }
  return res.json();
}

async function loadNotes(){
  try{
    const {sha,data}=await ghGetFile(NOTES_PATH);
    notesSha=sha;
    notesCache=Array.isArray(data)?data:[];
  }catch(e){
    console.error('notes load error',e);
    try{
      const r=await fetch('fx_notes.json?t='+Date.now());
      notesCache=r.ok?await r.json():[];
    }catch(e2){ notesCache=[]; }
  }
  const today=todayStr();
  const todayEntry=notesCache.find(n=>n.date===today);
  document.getElementById('note-textarea').value=todayEntry?(todayEntry.text||''):'';
  document.getElementById('note-token-hint').style.display=getGhToken()?'none':'block';
  renderNoteHistory();
}

async function saveNote(){
  if(!getGhToken()){ setupNoteToken(); if(!getGhToken()) return; }
  const text=document.getElementById('note-textarea').value;
  const today=todayStr();
  const priceInfo=(window.FXDATA&&window.FXDATA.prices&&window.FXDATA.prices.USDJPY)||{};
  const idx=notesCache.findIndex(n=>n.date===today);
  const entry={
    date: today,
    text: text,
    usdjpy_open:  priceInfo.today_open  ?? (idx>=0?notesCache[idx].usdjpy_open:null),
    usdjpy_close: priceInfo.today_close ?? (idx>=0?notesCache[idx].usdjpy_close:null),
    updated: new Date().toISOString(),
  };
  if(idx>=0) notesCache[idx]=entry; else notesCache.unshift(entry);
  notesCache.sort((a,b)=> a.date<b.date?1:-1);
  try{
    const result=await ghPutFile(NOTES_PATH, notesCache, notesSha, `相場ノート更新 ${today}`);
    notesSha=result.content.sha;
    const msg=document.getElementById('note-save-msg');
    msg.style.display='block';
    setTimeout(()=>msg.style.display='none',2500);
    renderNoteHistory();
  }catch(e){
    if(e.message==='NO_TOKEN'){ setupNoteToken(); return; }
    alert('保存に失敗しました: '+e.message);
  }
}

function renderNoteHistory(){
  const el=document.getElementById('note-history-list');
  const today=todayStr();
  const past=notesCache.filter(n=>n.date!==today && (n.text||'').trim());
  if(!past.length){ el.innerHTML='<div style="color:#4a5568;font-size:.8rem">過去のノートはまだありません</div>'; return; }
  el.innerHTML=past.map((n,i)=>{
    const id='note-'+i;
    const priceLine=(n.usdjpy_open!=null||n.usdjpy_close!=null)
      ?`<div style="font-size:.68rem;color:#3a4a5a;margin-top:4px">USD/JPY 始値 ${n.usdjpy_open??'—'} ／ 終値 ${n.usdjpy_close??'—'}</div>`:'';
    const safeText=(n.text||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
    return `<div style="border-bottom:1px solid #1a2332;padding:10px 0">
      <div onclick="toggleHist('${id}')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center">
        <div style="font-size:.85rem;font-weight:700;color:#c9d1d9">${n.date}</div>
        <div style="color:#4a5568;font-size:.8rem" id="arr-${id}">▶</div>
      </div>
      <div id="${id}" style="display:none;margin-top:8px">
        <div class="diary-text">${safeText}</div>
        ${priceLine}
      </div>
    </div>`;
  }).join('');
}

function renderNotePriceBar(d){
  const p=(d.prices&&d.prices.USDJPY)||{};
  const el=document.getElementById('note-price-bar');
  if(!el) return;
  if(p.today_open==null && p.today_close==null){
    el.textContent='価格データなし（次回自動更新時に反映されます）';
    return;
  }
  const diffTxt=p.diff_pct!=null?` （前日比 ${p.diff_pct>0?'+':''}${p.diff_pct}%）`:'';
  el.textContent=`始値 ${p.today_open??'—'} ／ 終値(現在値) ${p.today_close??'—'}${diffTxt}`;
}

window.addEventListener('load',fetchAll);
window.addEventListener('load',fetchMarkets);
window.addEventListener('load',fetchHistory);
window.addEventListener('load',loadNotes);
setInterval(fetchAll,30*60*1000);'''

    assert old_listeners in src, "❌ load listener 挿入位置が見つかりません（手動確認が必要です）"
    src = src.replace(old_listeners, note_js)

    backup(path)
    open(path, "w", encoding="utf-8").write(src)
    print("✅ index.html 更新完了")


def create_notes_json():
    path = os.path.join(BASE, "fx_notes.json")
    if os.path.exists(path):
        print("ℹ️ fx_notes.json は既に存在するためスキップ")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("[]")
    print("✅ fx_notes.json 新規作成")


if __name__ == "__main__":
    print(f"📂 作業ディレクトリ: {BASE}")
    for name in ("fx_fundamental.py", "index.html"):
        if not os.path.exists(os.path.join(BASE, name)):
            print(f"❌ {name} が見つかりません。fx-terminal リポジトリのルートで実行してください。")
            sys.exit(1)
    patch_fx_fundamental()
    patch_index_html()
    create_notes_json()
    print("\n🎉 パッチ適用完了。次のコマンドで反映してください:\n")
    print("  git add fx_fundamental.py index.html fx_notes.json")
    print("  git commit -m '相場ノート機能を追加'")
    print("  git pull --rebase -X ours origin main")
    print("  git push")
