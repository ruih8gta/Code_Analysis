# ジョブモデル（`*.job.json`）

複数のプログラムとJCLをまたいで、ジョブ全体を設計書として見せるためのモデル。パスはモデルファイルのあるフォルダーからの相対パス。

例：`batch-viewer/models/daily-job.job.json`

## 最上位

| キー | 必須 | 内容 |
|---|---|---|
| `id` / `title` | ○ | ジョブ群のIDと名前 |
| `dictionary` |  | データ辞書（プログラムビューワーと共有） |
| `copybooks` / `procs` |  | COPY句とカタログ式プロシージャのフォルダー |
| `jcl` | ○ | JCLファイル（配列） |
| `programs` | ○ | `{プログラムID: {source, viewer}}`。`viewer` はプログラムビューワーのHTML（相対リンク） |
| `steps` | ○ | 実行順のステップ（下記） |
| `datasets` |  | DSN ごとの名前・説明・編成・レイアウトの指定 |
| `overview` |  | `lead`、`summary` |
| `openItems` |  | 未確認事項 |

## steps

```json
{"id": "S2", "job": "POSTTRAN", "step": "STEP15", "program": "CBTRN02C", "title": "日次取引の計上", "desc": "…"}
```

- JCLのあるステップは `job` と `step` で特定する。同じ名前のステップが2つあれば `occurrence` で何番目かを指定する。PROC のステップは `procStep`。
- COBOLプログラムのステップは `program` を書くと、DD とプログラムの SELECT を突き合わせ、入出力文から CRUD を求める。DD が SELECT に無い、SELECT に対応する DD が無い、という食い違いは自動チェックに出る。
- ユーティリティ（SORT、IDCAMS など）は `utility: {DD名: "R"|"C"|"U"}` で入出力を書く。制御文が無いなど推定のときは `utilityNote` に理由を書く。
- JCL の無いステップは `assumed: true` と `ddMap: {DD名: DSN}`、`note` を書く。画面では破線と「推定」で示す。

## datasets

```json
"AWS.M2.CARDDEMO.TRANSACT.BKUP": {"name": "取引バックアップ", "kind": "順次（世代）", "layoutFrom": "AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS", "desc": "…"}
```

- 世代番号 `(+1)` などは外して同じデータセットとして扱い、世代であることは表示で示す。
- レイアウトは、そのデータセットを READ INTO・WRITE FROM するプログラムのレコードから自動で決める。決まらないときは `layoutRecord`（どれかのプログラムにあるレコード名）か `layoutFrom`（同じレイアウトの別の DSN）を書く。

## 自動で求めるもの

| 内容 | 求め方 |
|---|---|
| データセット単位のCRUD | READ=R、WRITE=C、REWRITE=U、DELETE=D、OPENだけ=O。OPEN OUTPUT で WRITE が見つからなければ C |
| 項目単位のCRUD（推定） | Rは項目名を参照する行、Uは代入先（TO・COMPUTE・GIVING・INITIALIZE・INTO・SUBTRACT … FROM）になる行。Cはレコードを書くとき全項目。OF／IN で別レコードに修飾された参照は数えない |
| DFD の配置 | ステップを横一列に並べ、ジョブ内で読むだけのデータセットを上段、作成・更新するものを下段に置く |
| 自動チェック | 仮置きのステップ、ステップ名の重複、DD と SELECT の食い違い、レイアウト不明、ジョブの外とやり取りするデータ |
