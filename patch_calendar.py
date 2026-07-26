#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_calendar.py -- index.html のカレンダーに fx_calendar_extra.json を統合する

index.html 末尾の buildCalendar(); の直前にマージ処理を差し込む。
IND と同じスコープに入れるため、別の <script> ブロックにはしない
（IND が IIFE の中にあっても確実に届く）。

  python3 patch_calendar.py            # 差分を表示するだけ（安全確認）
  python3 patch_calendar.py --apply    # バックアップを取って実際に書き換え
  python3 patch_calendar.py --revert   # 直近のバックアップに戻す

さらに --workflow を付けると .github/workflows/main.yml にも実行ステップを追加する。
"""

import os
import re
import io
import sys
import glob
import difflib
import datetime as dt

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE, "index.html")
WF = os.path.join(BASE, ".github", "workflows", "main.yml")
MARK = "calendar-extra"

SNIPPET = """
  /* ===== 追加カレンダー(fx_calendar_extra.json)を IND へ統合 : calendar-extra ===== */
  (function(){
    function starRank(s){ var m = /^(\\u2605+)/.exec(String(s)); return m ? m[1].length : 0; }
    function byStar(a, b){ return starRank(b) - starRank(a); }

    /* 既存エントリの型を調べる。buildCalendar が配列前提か文字列前提かを判定する */
    function detectShape(obj){
      for(var k in obj){
        if(Object.prototype.hasOwnProperty.call(obj, k) && obj[k] != null){
          return Array.isArray(obj[k]) ? 'array' : 'string';
        }
      }
      return 'array';
    }

    fetch('fx_calendar_extra.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(d){
        var shape = detectShape(IND), added = 0;
        (d.events || []).forEach(function(e){
          if(!e.date || !e.short) return;
          var cur = IND[e.date];
          var isArr = Array.isArray(cur) || (cur == null && shape === 'array');
          if(isArr){
            var arr = Array.isArray(cur) ? cur : (cur == null || cur === '' ? [] : [cur]);
            if(arr.indexOf(e.short) < 0){ arr.push(e.short); arr.sort(byStar); added++; }
            IND[e.date] = arr;
          } else {
            var parts = (cur == null || cur === '') ? [] : String(cur).split(' / ');
            if(parts.indexOf(e.short) < 0){
              parts.push(e.short);
              parts.sort(byStar);
              IND[e.date] = parts.join(' / ');
              added++;
            }
          }
        });
        console.log('[calendar-extra] ' + added + '件を追加 (形式:' + shape + ') / 生成 '
                    + (d.generated_at_jst || '?'));
        /* IND を読む描画関数を再実行。片方が失敗しても もう片方は動かす */
        try { if(typeof buildCalendar === 'function') buildCalendar(); }
        catch(x){ console.warn('[calendar-extra] buildCalendar 失敗:', x.message); }
        try { if(typeof renderTodayBar === 'function') renderTodayBar(); }
        catch(x){ console.warn('[calendar-extra] renderTodayBar 失敗:', x.message); }
      })
      .catch(function(err){ console.warn('[calendar-extra] 読み込み失敗:', err.message); });
  })();
  /* ===== calendar-extra ここまで ===== */
"""

START_MARK = "/* ===== 追加カレンダー(fx_calendar_extra.json)を IND へ統合 : calendar-extra ===== */"
END_MARK = "/* ===== calendar-extra ここまで ===== */"

WF_STEP = ("%s- name: Update calendar extra (BOJ/ECB/CPI/PMI/Mag7)\n"
           "%s  run: python fx_calendar_extra.py\n"
           "%s  continue-on-error: true\n")


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def show_diff(old, new, name):
    d = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                  "%s (現在)" % name, "%s (変更後)" % name, lineterm=""))
    print("\n".join(d) if d else "(差分なし)")


# --------------------------------------------------------------------------
def strip_block(src):
    """既に挿入済みのブロックを取り除く（再適用できるようにする）。"""
    i = src.find(START_MARK)
    if i < 0:
        return src, False
    j = src.find(END_MARK, i)
    if j < 0:
        return src, False
    j += len(END_MARK)
    # 行頭のインデントと、その前の改行1個までを一緒に落とす。
    # 末尾側の改行は残す（次行の buildCalendar(); が前行と繋がってしまうため）。
    while i > 0 and src[i - 1] in " \t":
        i -= 1
    if i > 0 and src[i - 1] == "\n":
        i -= 1
    return src[:i] + src[j:], True


def patch_index(src):
    src, replaced = strip_block(src)
    prefix = "既存ブロックを差し替え → " if replaced else ""

    # 末尾の単独 buildCalendar(); を探す（showTab内の呼び出しではないもの）
    cands = [m for m in re.finditer(r"\n([ \t]*)buildCalendar\(\);", src)]
    if not cands:
        return None, "buildCalendar(); の呼び出しが見つかりません"
    m = cands[-1]
    indent = m.group(1)
    body = "\n".join(indent + l[2:] if l.startswith("  ") else indent + l
                     for l in SNIPPET.strip("\n").splitlines())
    out = src[:m.start()] + "\n" + body + src[m.start():]

    if MARK not in out:
        return None, "挿入に失敗しました"
    return out, "%sbuildCalendar(); の直前（%d文字目, インデント%d）に挿入" % (
        prefix, m.start(), len(indent))


def patch_workflow(src):
    if "fx_calendar_extra.py" in src:
        return None, "すでに追記済み"
    steps = list(re.finditer(r"^([ \t]*)-[ \t]+name:.*$", src, re.M))
    target = None
    for i, m in enumerate(steps):
        end = steps[i + 1].start() if i + 1 < len(steps) else len(src)
        if re.search(r"python3?\s+\S*\.py", src[m.start():end]):
            target = (m.group(1), end)
    if not target:
        return None, ".py を実行するステップが見つかりません"
    indent, pos = target
    block = WF_STEP % (indent, indent, indent)
    return src[:pos] + block + src[pos:], "最後のPython実行ステップの直後に追加"


# --------------------------------------------------------------------------
def do_revert():
    baks = sorted(glob.glob(INDEX + ".bak-*"))
    if not baks:
        print("バックアップが見つかりません")
        return 1
    latest = baks[-1]
    write(INDEX, read(latest))
    print("復元しました: %s → index.html" % os.path.basename(latest))
    return 0


def main():
    args = set(sys.argv[1:])
    if "--revert" in args:
        sys.exit(do_revert())

    apply_ = "--apply" in args
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    if not os.path.exists(INDEX):
        print("index.html が見つかりません: %s" % INDEX)
        sys.exit(1)
    if not os.path.exists(os.path.join(BASE, "fx_calendar_extra.json")):
        print("! fx_calendar_extra.json がありません。先に実行してください:")
        print("    python3 fx_calendar_extra.py")
        sys.exit(1)

    print("=" * 70)
    print(" index.html へのカレンダー統合  %s" % ("(適用)" if apply_ else "(プレビューのみ)"))
    print("=" * 70)

    src = read(INDEX)
    new, msg = patch_index(src)
    print("  %s" % msg)
    if new:
        show_diff(src, new, "index.html")
        if apply_:
            bak = INDEX + ".bak-" + stamp
            write(bak, src)
            write(INDEX, new)
            assert MARK in read(INDEX), "書き込み検証に失敗"
            print("\n  ✓ 適用しました (backup: %s)" % os.path.basename(bak))

    if "--workflow" in args:
        print("\n" + "=" * 70)
        print(" GitHub Actions への追記")
        print("=" * 70)
        if not os.path.exists(WF):
            print("  %s が見つかりません" % WF)
        else:
            wsrc = read(WF)
            wnew, wmsg = patch_workflow(wsrc)
            print("  %s" % wmsg)
            if wnew:
                show_diff(wsrc, wnew, "main.yml")
                if apply_:
                    write(WF + ".bak-" + stamp, wsrc)
                    write(WF, wnew)
                    print("\n  ✓ 適用しました")

    if not apply_:
        print("\n" + "-" * 70)
        print("実際に適用するには:  python3 patch_calendar.py --apply --workflow")
        print("元に戻すには:        python3 patch_calendar.py --revert")
    else:
        print("""
次の手順:
  1) ローカル確認
       python3 -m http.server 8000
       → http://localhost:8000  カレンダータブを開く
       → ブラウザのコンソールに [calendar-extra] N件を追加 と出れば成功
  2) push
       git add fx_calendar_extra.py fx_calendar_extra.json index.html \\
               .github/workflows/main.yml
       git commit -m "カレンダーに日銀/ECB/日本CPI/欧PMI/Mag7決算を追加"
       git pull --rebase -X ours
       git push
""")


if __name__ == "__main__":
    main()
