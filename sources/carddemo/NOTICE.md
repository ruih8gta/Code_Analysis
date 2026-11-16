# 取得元

このフォルダーのファイルは、[aws-samples/aws-mainframe-modernization-carddemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo) のコミット `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e` から、内容を変えずに取得しました。Apache License 2.0 で提供されています（[LICENSE](LICENSE)）。

| フォルダー | 内容 | 取得元のパス |
|---|---|---|
| `cbl/` | CBTRN02C（日次取引の計上）、CBTRN03C（取引明細レポート） | `app/cbl/` |
| `cpy/` | 上記と CBTRN01C が使う COPY 句 | `app/cpy/` |
| `jcl/` | POSTTRAN、TRANREPT | `app/jcl/` |
| `proc/` | REPROC（TRANREPT が呼ぶカタログ式プロシージャ） | `app/proc/` |

CBTRN01C の原本は [`original/CBTRN01C.cbl`](../../original/CBTRN01C.cbl) にあります。CBTRN01C を実行する JCL は取得元にありません。REPROC が読む制御文 `CNTLLIB(REPROCT)` も取得元にないため、IDCAMS の処理内容は推定です。
