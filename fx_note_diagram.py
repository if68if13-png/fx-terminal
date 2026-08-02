#!/usr/bin/env python3
"""相場ノートの本文から図解データ（構造化JSON）を生成して fx_notes.json に書き戻す。"""
import anthropic, hashlib, json, os, re, sys

ANALYSIS_DIR = os.environ.get("SAVE_DIR", os.path.dirname(os.path.abspath(__file__)))
NOTES_JSON = os.path.join(ANALYSIS_DIR, "fx_notes.json")
MODEL = "claude-sonnet-5"
MAX_NOTES = 5
MIN_LEN = 120

SCHEMA = """{
  "title": "図解の見出し（本文の内容を15文字前後で）",
  "headline": {"from": "起点の値", "to": "着地の値", "note": "一言補足"},
  "timeline": [
    {"date": "7/30", "items": [
      {"icon": "🇯🇵", "text": "出来事の要約（30文字以内）", "subs": ["補足", "補足"]}
    ]}
  ],
  "keypoints": [
    {"verdict": "○ または × または ！", "label": "対象（10文字以内）", "text": "結論（30文字以内）"}
  ],
  "keypoints_note": "keypoints 全体の理由・補足（60文字以内）",
  "views": [
    {"term": "短期", "dir": "up|down|flat", "label": "円高（ショート）", "text": "根拠（40文字以内）"}
  ],
  "levels": {"label": "ショートのテクニカルポイント", "steps": ["157.5", "155円台", "152円台"]},
  "policy": "運用方針の要約（60文字以内）",
  "chains": [
    {"steps": ["きっかけ", "次に起きたこと", "その次"], "conclusion": "落としどころ（40文字以内）"}
  ]
}"""

PROMPT = """あなたはFXトレーダーの相場ノートを、FX初心者にも一目でわかる図解データに変換するアシスタントです。

以下は筆者本人が書いた相場ノートの本文です。

<note>
{text}
</note>

このノートを、下記スキーマのJSONに要約してください。

<schema>
{schema}
</schema>

厳守すること:
- 本文に書かれている内容だけを使う。数値・固有名詞・出来事を絶対に創作しない。
- 数値は本文の表記をそのまま使う（157.5円 / 4.7%台 / 86.8ドル など）。
- 筆者の判断や結論は、筆者の立場のまま書く。第三者的に薄めたり、一般論に置き換えたりしない。
- 該当する内容が本文に無いキーは、キーごと省略する（空配列・空文字を入れない）。
- timeline は日付や時系列がはっきり書かれている場合のみ。無ければ省略。
- keypoints は「今回はっきりしたこと」「学び」にあたる部分。無ければ省略。
- chains は「AだからB、BだからC」という因果の連鎖。1本3〜4ステップ程度。無ければ省略。
- icon は国旗（🇯🇵🇺🇸🇰🇷🇪🇺🇬🇧）か 📄📈📉🛢️💬💰 から本文に合うものを選ぶ。迷ったら省略。
- dir は、その通貨ペアが上に行く見立てなら up、下なら down、方向感なしなら flat。
- 全体で読み切れる分量にする。timeline は最大3日分、各日 items 最大6件、chains は最大3本。

JSONのみを出力してください。前置き・説明・コードフェンスは不要です。"""


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("JSONが見つかりません")
    return json.loads(raw[start:end + 1])


def build_diagram(client, text):
    res = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": PROMPT.format(text=text, schema=SCHEMA)}],
    )
    return extract_json(res.content[0].text)


def main():
    if not os.path.exists(NOTES_JSON):
        print("  fx_notes.json が見つかりません。スキップします。")
        return
    with open(NOTES_JSON, encoding="utf-8") as f:
        notes = json.load(f)
    if not isinstance(notes, list):
        print("  fx_notes.json の形式が想定外です。スキップします。")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ANTHROPIC_API_KEY が未設定です。スキップします。")
        return
    client = anthropic.Anthropic()

    updated = 0
    for note in notes[:MAX_NOTES]:
        text = (note.get("text") or "").strip()
        if len(text) < MIN_LEN:
            continue
        h = sha(text)
        if note.get("diagram") and note.get("diagram_hash") == h:
            continue
        try:
            note["diagram"] = build_diagram(client, text)
            note["diagram_hash"] = h
            updated += 1
            print(f"  OK {note.get('date')} の図解を生成しました")
        except Exception as e:
            print(f"  NG {note.get('date')} の図解生成に失敗: {e}")

    if updated:
        with open(NOTES_JSON, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        print(f"  fx_notes.json を更新しました（{updated}件）")
    else:
        print("  更新対象はありませんでした")


if __name__ == "__main__":
    main()
