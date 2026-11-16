# バッチ設計ビューワー

COBOLバッチを、設計書の順（概要 → ジョブフロー → DFD → DB・ファイル一覧 → データ項目定義 → 処理フロー → 例外 → 網羅）で読めるようにした単独HTMLです。ブラウザーで開くだけで動きます（フォント以外の外部通信なし）。

| ファイル | 内容 |
|---|---|
| [CBTRN01C.html](CBTRN01C.html) | プログラムビューワー。1本のプログラムの処理フロー・DFD・DB一覧・データ項目定義を共通IDでつなぐ |
| [daily-job.html](daily-job.html) | ジョブビューワー。CBTRN01C・CBTRN02C・CBTRN03C と POSTTRAN・TRANREPT をまたいで、DFD・DB一覧・CRUD図・データ項目定義をまとめる |
| [models/](models/) | 人とエージェントが書くモデル（業務上の名前、処理のまとまり、例外、仮定） |
| [dictionary.json](dictionary.json) | COBOL項目名 → データ項目名の辞書（両方のビューワーで共有） |

作り方と、モデルの書き方は [batch-design-viewer スキル](../.agents/skills/batch-design-viewer/SKILL.md) にあります。HTML はモデルとソースから生成するので、直接編集しません。

```sh
S=.agents/skills/batch-design-viewer/scripts
python -X utf8 $S/build_viewer.py program batch-viewer/models/CBTRN01C.program.json --out batch-viewer/CBTRN01C.html
python -X utf8 $S/build_viewer.py job batch-viewer/models/daily-job.job.json --out batch-viewer/daily-job.html
node $S/smoke_test.js batch-viewer/CBTRN01C.html batch-viewer/daily-job.html
```

ジョブの構成には仮定を含みます。CBTRN01C には JCL が無いため、POSTTRAN の前に流す事前チェックとして仮に置いています。TRANREPT を POSTTRAN の後に流す順序も仮定です（取得元ではオンライン画面から投入）。仮定の箇所は画面で破線と「推定」「仮置き」で示し、「網羅と未確認」に一覧しています。項目単位の CRUD は、項目名の参照と代入先からの推定です。
