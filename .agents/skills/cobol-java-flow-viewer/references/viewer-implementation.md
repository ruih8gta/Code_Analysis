# 工程別ビューアーの実装メモ

[動作例](../assets/carddemo/viewer.html)は、単独HTML内にCSS、JavaScript、原本・Javaの全文、架空データ、COPY句抽出定義、処理・項目の対応台帳を含む。工程別の見せ方とコード連動を参考にする。固定行番号やCardDemoの業務判断を別対象へ流用しない。

## 画面とデータ

| 箇所 | 役割 |
|---|---|
| `setupReview / setReviewStage` | 全体像、現行仕様、新旧比較、項目対応の切替。現行仕様ではJavaを隠す |
| `renderOverview` | 工程ごとの問い、未確認事項、対象の版、判断の限界 |
| `blocks / connections / traces` | 現行の要約フローと再構成したケース。網羅済みの完全なCFGではない |
| `sourceRanges / conditionLines` | フロー、条件、呼出元の根拠行 |
| `showSourceOrigins` | 原本の行から対応する図の候補、未登録一覧への移動 |
| `buildAudit` | この固定版の段落・判定候補と、既存フローの範囲登録を抽出 |
| `buildSourceCoverage / renderAudit` | 原本の全行を順に分類し、フロー・条件・入出力の関連と未登録を一覧化 |
| `selectSourceLine / sourceOriginBanner` | 行番号からの選択、対応先を開いた後の元の行への復帰 |
| `renderSourceInspector` | 選択範囲の原本、外側も含めた条件の所属・真偽、I/O・変数定義の根拠 |
| `review-data / renderComparisons` | 処理ごとの新旧根拠、差分、確認事項、関連項目 |
| `renderTestEvidence` | モデル対Java、Java単体、新旧の直接実行比較の区別 |
| `renderMappings` | レコード・制御変数・ファイルの対応、変換、未整理箇所 |
| `layouts / renderDictionary` | 6入力71項目の定義スナップショット。COPY句全文ではない |
| `renderSource / setPaneRanges` | ソース全文表示、1始まり行範囲の強調、対応なしの明示 |
| `verification-data / validateAuditEvidence` | 保存した検証証拠と、ソース・ケース・台帳・定義・アプリのハッシュ照合 |

画面は`#overview`、`#legacy`、`#coverage`、`#compare`、`#data`から開ける。検索・絞り込みで該当なしになったときは、前の根拠コードを表示したままにしない。

網羅性の点検は`.workspace.is-audit`で幅いっぱいの原本・対応一覧に切り替える。別の原本ペインは詳細を開いたときに再表示する。一覧には各行の固定形式の本文をすべて表示し、抜粋の省略でコードを隠さない。基本のコード文字サイズは14pxで、狭い画面では対応ボタンを各範囲の下へ配置する。「見方・対象範囲」と選択範囲の追加説明は折りたたむ。`?line=173#coverage`のようなリンクで確認箇所を直接開ける。

## プロジェクト側の生成・検証

- `scripts/build_review_model.py`：CardDemoの固定版に対する台帳を生成し、HTMLへ埋め込む。原本・Javaのハッシュが変われば停止する。ハッシュだけを更新せず、対応と差分を再レビューする。
- `scripts/source_coverage.js / sync_source_coverage.py`：行順点検の実装を単独HTMLの指定区間へ埋め込む。編集後は同期してから証拠を更新する。
- `scripts/verify_viewer.py`：埋込ソースと実ファイル、台帳の一致、相互参照、行範囲、ケースと図、Javaの実行結果を確認する。全494行の欠落・重複と、条件の所属、I/O参照先も確認する。`--update`で証拠と`review/source-coverage.json`を保存する。
- `scripts/qa_viewer_browser.py`：ローカルで工程切替、コード連動、検索、図への逆参照、行順一覧から各対応先への往復、証拠の表示と画面幅を検証する。`--stage coverage`は173行を選択した画面を保存する。

これらはこのプロジェクトの補助で、スキル内の必須ランタイムではない。別プロジェクトでは利用環境に合う検証を作る。ブラウザー操作には利用可能な対応ツールを使い、制限や未確認箇所を正確に報告する。

ソースやJSONを埋め込む際はJSONシリアライズでエスケープし、script内の`<`を`\u003c`へ置換する。コードの描画はtextContentを使う。表示・行番号・実ファイルを一致させる。

## この例で維持すべき意味

原本CBTRN01Cは日次取引のカード・口座を照合する。6入力を開くが、CUSTFILE・CARDFILE・TRANFILEは開閉のみで、ファイル更新はしない。コメントだけで更新バッチと解釈しない。

EOFガードの内側は取引のDISPLAYだけで、EOF後も照合が走る。Javaはこれを再現する一方、空入力の作業領域を空白とする前提は旧ランタイムで未確認。条件式の真偽が逆でも、カード・口座の登録あり／なしの行き先を比較する。

Map／Setの事前読込、CLOSEの逆順、異常終了の診断・出力先・終了コードは差分として扱う。日次取引CLOSE失敗時に原本が顧客の文言・状態を参照する点も、原本不整合の候補として残す。

既存の要約図は18段落中7段落に対応範囲がある。15本の定義済み接続を再構成ケースでたどれても、原本全体の網羅は未達である。UIの完成やJavaログの一致を、旧環境と実行比較したことにしない。

行順の点検は全494行を保持する。実行部309行（段落名・区切り含む）のフロー登録は93行、未登録は216行。残りは定義96行とコメント・空行・宣言89行。判定のケース登録は8/36で、各行に関係する外側の条件も一覧から確認する。これは固定版に対する簡易解析で、COPY展開、JCL、完全なCOBOL構文には対応しない。分類済み・リンク登録・意味の確認・実行通過を同じ指標にしない。

例に含まれるAWS由来部分を再利用する際は、[LICENSE](../assets/carddemo/LICENSE)と[NOTICE](../assets/carddemo/NOTICE)を維持する。
