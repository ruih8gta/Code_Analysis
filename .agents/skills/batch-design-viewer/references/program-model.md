# プログラムモデル（`*.program.json`）

1本のCOBOLプログラムを設計書として見せるためのモデル。パスはモデルファイルのあるフォルダーからの相対パス。ソースから取れる事実（SELECT・レイアウト・入出力文・段落・各項目の使用行）は `build_viewer.py` が抽出するので、モデルには書かない。

例：`batch-viewer/models/CBTRN01C.program.json`

## 最上位

| キー | 必須 | 内容 |
|---|---|---|
| `program` / `title` / `type` | ○ | プログラムID、業務上の名前、種類（例 `BATCH COBOL`） |
| `source` | ○ | 原本のパス |
| `copybooks` |  | COPY句のフォルダー（配列） |
| `dictionary` |  | データ辞書のパス（COBOL項目名 → データ項目名） |
| `links.job` |  | ジョブビューワーへのリンク `{href, label}` |
| `overview` | ○ | `summary`（[見出し, 値] の配列）と `checks`（合意観点のカード） |
| `context` | ○ | ジョブフロー画面の前後ジョブ `prev` `next`、追加の出力 `outputs`、注記 `note` |
| `stores` | ○ | データストア（下記） |
| `flow` | ○ | 処理フロー（下記） |
| `dfd` | ○ | DFD（下記） |
| `errors` |  | 例外の一覧 |
| `patterns` / `workArea` |  | 処理パターンと、表示する作業領域の見出し |
| `openItems` |  | 未確認事項 |

`checks` の `status` は `ok`（根拠あり）、`warn`（要確認・推定）、`none`（未確認）。表示文言は `label` に書く。

## stores

```json
{"dd": "XREFFILE", "no": "D2", "name": "カード索引", "nodes": ["open", "xref", "xres", "close"]}
```

- `dd` は SELECT の ASSIGN 先。編成・キー・レコード長・COPY句・CRUD・入出力文は抽出結果から補われる。
- `nodes` は、このデータストアに関係する処理フローの箱。
- 開くだけで READ INTO などが無いファイルはレイアウトが決まらないので、`layoutRecord` にCOPY句のレコード名を書く。

## flow

```json
{"id": "xref", "type": "pre", "lane": "main", "row": 5, "label": "カード番号で索引を引く",
 "sub": "2000-LOOKUP-XREF", "lines": [[170, 172], [227, 229]], "orig": "2000-LOOKUP-XREF", "desc": "…"}
```

- `type`：`term`（端子）、`proc`（処理）、`pre`（段落の呼出し）、`dec`（判断）。
- `lane`：`main`（正常系）、`right`（エラー・未登録）、`left`（EOF など）。`row` は上から数えた段。座標は書かない。
- `kind`：`warn`・`err` で色が変わる。`routine` で定型処理の表（`flow.routines`）を結ぶ。
- `lines` は根拠の行範囲。網羅の画面は、ここに含まれた行を「図に対応」と数える。
- `edges` は `{from, to, label, kind, dash}`。経路は自動で引く。主レーンで上へ戻る線は左端を通り、右レーンへの線は途中の箱を避けて右側を通る。
- `notes` は図の注記 `{lane, row, title, lines}`。
- `routines.<名前>` は `{columns, rows, diffRows, note, sample: [開始行, 終了行], highlight}`。

## dfd

```json
{"externals": [{"id": "E1", "name": "前工程", "sub": "…", "x": 10, "y": 40, "w": 170, "h": 52, "desc": "…"}],
 "processes": [{"id": "P2", "name": ["カードを", "照合する"], "x": 520, "y": 200, "nodes": ["xref", "xres", "skip"], "para": "2000-LOOKUP-XREF", "desc": "…"}],
 "stores": {"XREFFILE": [430, 40]},
 "flows": [{"id": "F3", "from": "D:XREFFILE", "to": "P:P2", "name": "カード索引レコード",
            "items": ["XREFFILE.XREF-CARD-NUM", "XREFFILE.XREF-ACCT-ID"], "lines": [[228, 230]],
            "labelAnchor": "start", "labelOffset": [8, 4], "note": "…", "est": false}]}
```

- 座標は1000×500の図の中の位置（プロセスは中心、外部とデータストアは左上）。
- `items` は `DD名.COBOL項目名`。レコード全体なら `DD名.*`。
- `est: true` は推定の流れで、破線になる。

## errors と patterns

- `errors`：`{event, where, cond, output, after, level, node}`。`node` は処理フローの箱で、行を押すとそこへ移る。
- `patterns.<名前>.steps`：`{node, edge: "from>to", info, log: [...], ws: {...}, flag}`。ソースとサンプルから再構成した順で、実行結果ではないことを `note` に書く。

## 検証される内容

存在しない箱・線・データストア・項目・行範囲を参照すると、`build_viewer.py` は何も書き出さずに止まる。
