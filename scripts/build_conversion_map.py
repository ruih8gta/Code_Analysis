"""Build the CardDemo conversion ledger: how each COBOL line was converted to Java.

Every COBOL line belongs to exactly one conversion unit, or is a comment/blank line.
Every Java line derives from at least one unit, or is scaffolding (import, brace,
comment, blank). This is a hand-reviewed ledger for the pinned sources, not a parser.
Changed sources require re-reviewing the ranges, not just updating a hash.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASIS = {'cobol': '55c2aebd59528aa42b28878ba5ca4d17a00b3548fc25e4ce1529710d366fd576',
         'java': 'c24845f18a0f1a8db729904eea75749d43a67d8380f38e468b4279b2326277a3'}

KINDS = [
    ('direct', '構文の置換', '文や宣言がほぼ1対1でJavaの構文に置き換わる。'),
    ('restructured', '構造の組み替え', 'フラグ・状態コード・段落分割を、Javaの制御構造やメソッドへ組み替える。'),
    ('replaced', '仕組みの置換', 'ファイル編成・レコード領域・異常終了などを、Javaの別の仕組みで実現する。'),
    ('consolidated', '定型の集約', '繰り返し書かれた定型処理を、共通メソッドや言語機能にまとめる。'),
    ('dropped', '変換先なし', 'Javaに対応するコードがない。'),
    ('added', 'Javaで追加', 'COBOLに由来する文がなく、Java側で新しく加えた。'),
]


def unit(id, title, kind, old, new, pattern, note, reviews=()):
    return dict(id=id, title=title, kind=kind, oldRanges=old, newRanges=new,
                pattern=pattern, note=note, reviewIds=list(reviews))


UNITS = [
    unit('header', 'ヘッダー・ライセンス表記', 'direct', [[1, 21]], [[1, 3]],
         '注記行（*）→ 行コメント（//）',
         'プログラムの説明と著作権・ライセンス表記を3行に要約。版数の行（493）はコメントとして対象外。'),
    unit('program', 'プログラムの宣言', 'direct', [[22, 24]], [[17, 17], [138, 138]],
         'PROGRAM-ID → final class',
         'プログラム名CBTRN01Cはクラス名にせず、役割を表すDailyTransactionLookupへ改名。開始・終了ログには原本の名前が残る。'),
    unit('file-control', 'ファイルの割当て', 'replaced', [[26, 62]], [[46, 51], [59, 61]],
         'SELECT … ASSIGN TO DD名 → データフォルダー内の固定ファイル名',
         'DD名（JCLで実ファイルへ結ぶ）は、引数のフォルダーと固定のファイル名に変わる。編成（順／索引）・アクセスモード・レコードキーの宣言はJavaにはなく、読み方の違いとして各処理に現れる。',
         ['open']),
    unit('fd-records', 'FDのレコード領域', 'replaced', [[64, 94]], [[20, 20], [67, 67], [82, 82], [97, 97]],
         'FDの固定長バッファ → readLine()のString',
         'ファイルごとの固定長領域は持たず、1行を文字列で受ける。レコード長は日次取引の350桁だけが定数に残り、索引50桁・口座300桁は行長検査の上限値として現れる。'),
    unit('copy-daily', '日次取引レコードの定義', 'replaced', [[99, 99]], [[19, 22]],
         'COPY句のレコードレイアウト → 桁位置の定数＋substring',
         'CVTRA06Yの全項目のうち、Javaが個別に取り出すのは取引ID（1〜16桁）とカード番号（263〜278桁）だけ。残りは350桁の文字列のまま保持・表示する。',
         ['read']),
    unit('copy-xref', 'カード索引レコードの定義', 'replaced', [[109, 109]], [[25, 25], [70, 71]],
         'COPY句のレコードレイアウト → record型＋substring',
         'CVACT03Yのカード番号をMapのキーに、顧客ID・口座IDをCrossReferenceに保持。数値PICのIDも先頭ゼロを保つため文字列のまま扱う。',
         ['card']),
    unit('copy-account', '口座レコードの定義', 'replaced', [[119, 119]], [[23, 23], [85, 85]],
         'COPY句のレコードレイアウト → 主キーの長さの定数',
         'CVACT01Yのうち使うのは先頭11桁の口座IDだけ。残高などの項目はJavaに保持しない。',
         ['account']),
    unit('copy-unused', '項目を使わない3ファイルの定義', 'dropped', [[104, 104], [114, 114], [124, 124]], [],
         'COPY句 → 対応なし',
         '顧客・カード・既存取引のレコード定義（CVCUS01Y・CVACT02Y・CVTRA05Y）。原本も開閉するだけで項目を参照しないため、Javaには定義を置いていない。'),
    unit('file-status', 'ファイル状態コード', 'replaced',
         [[96, 96], [100, 102], [105, 107], [110, 112], [115, 117], [120, 122], [125, 127]], [[35, 35]],
         'FILE STATUS（2桁）→ IOException',
         '6ファイル分の状態コード領域は持たない。成功は通常の戻り、失敗は例外になる。状態コードの値そのものはJavaでは取得できない。',
         ['errors']),
    unit('status-display', '状態コードの整形表示', 'replaced', [[129, 140], [476, 489]], [[36, 36]],
         'Z-DISPLAY-IO-STATUS → 例外メッセージの表示',
         '「FILE STATUS IS: NNNN」の整形（バイナリ変換を含む）は再現せず、例外のメッセージを標準エラーへ出す。診断文と出力先が変わる。',
         ['errors']),
    unit('result-code', '処理結果コードと条件名', 'restructured', [[142, 144]], [[97, 97]],
         'APPL-RESULT（0／16／12）と88レベル → ループ継続・null・例外',
         '結果を数値で持ち回らず、制御の流れそのもので表す。APPL-AOK・APPL-EOFに当たる変数はない。'),
    unit('eof-flag', 'EOFフラグ', 'restructured', [[146, 146]], [[97, 97], [105, 105]],
         "END-OF-DAILY-TRANS-FILE（'N'／'Y'）→ for文の終了条件",
         'フラグ変数をなくし、readLine()がnullを返すことをEOFとする。EOF後にも1回照合する原本の動きは、ループの後の1文で再現。',
         ['eof']),
    unit('abend', '異常終了', 'replaced', [[147, 148], [469, 473]], [[37, 38]],
         "CALL 'CEE3ABD'（ABCODE 999）→ 標準エラー＋System.exit(1)",
         '異常コード999はメッセージの文言に残るだけで、プロセスの終了コードは1。TIMINGに当たる値はない。',
         ['errors']),
    unit('lookup-status', '照合結果のステータス', 'restructured', [[149, 151]], [[112, 112], [123, 123]],
         'WS-XREF／ACCT-READ-STATUS（0／4）→ null判定・containsの真偽',
         '段落から呼出元へ結果を渡す作業変数をなくし、検索結果をその場で判定する。',
         ['card', 'account']),
    unit('main', 'メイン処理の開始と終了', 'direct', [[154, 156], [195, 197]], [[27, 27], [33, 34], [44, 45], [56, 56]],
         'MAIN-PARA・DISPLAY・GOBACK → main／run・println・return',
         '開始・終了ログの文言は同じ。出力先を引数で受けるためにrun()へ分けている。'),
    unit('open', '6ファイルを開く', 'consolidated', [[157, 162], [252, 359]], [[46, 51], [59, 61]],
         'OPEN段落×6（各17行）→ open()ヘルパー＋try-with-resources',
         '同じ形の段落6つが、1つのメソッドと6行の宣言になる。開く順序は同じ。失敗時の「ERROR OPENING …」と状態表示は、例外の伝播に置き換わる。',
         ['open', 'errors']),
    unit('loop', '読込ループ', 'restructured', [[164, 165], [185, 186]],
         [[54, 54], [93, 94], [97, 97], [101, 101], [105, 105], [108, 109]],
         'PERFORM UNTIL＋フラグ判定 → for文＋メソッド抽出',
         'ループ本体の照合部分をcheckTransaction()へ切り出し、ループ内とEOF後の2か所から呼ぶ。原本ではEOFの回もループ本体を通るために起きる再照合を、Javaでは明示的な呼出しとして書いている。',
         ['eof']),
    unit('read', '日次取引を1件読む', 'replaced', [[166, 166], [202, 203]], [[95, 95], [97, 97], [99, 99]],
         'READ … INTO 作業領域 → readLine()＋350桁へ空白補完',
         '作業領域に当たるcurrentは空白350桁で初期化する。行末を省いた入力も受けるため、右側を空白で埋める。原本の作業領域の初期値は未確認。',
         ['read', 'eof']),
    unit('read-status', '読込結果の振り分け', 'restructured', [[204, 225]], [[35, 35], [97, 97]],
         "状態 '00'／'10'／その他 のIF連鎖 → 行あり／null／IOException",
         '22行の判定が、for文の条件と例外の伝播に吸収される。読込エラー時の「ERROR READING …」の文言はJavaにない。',
         ['read', 'errors']),
    unit('display-record', '取引レコードの表示', 'direct', [[167, 169]], [[100, 100]],
         'DISPLAY レコード → println',
         'EOFでないときだけ表示するIFは、Javaではループの中に置くことで同じ意味になる。',
         ['read']),
    unit('xref-read', 'カード索引の検索', 'replaced', [[170, 172], [227, 230]],
         [[52, 52], [64, 67], [70, 72], [76, 76], [110, 111]],
         'VSAMのキー読込（READ … KEY IS）→ 事前に作ったMapのget',
         '取引のたびにファイルを引く代わりに、最初に索引全体をMapへ読み込む。読む時点・メモリ使用量・異常の検知時点が変わる。',
         ['card', 'master-timing']),
    unit('xref-missing', 'カード未登録の経路', 'restructured', [[173, 173], [180, 184], [231, 233]], [[112, 116]],
         'INVALID KEYでステータス設定 → 呼出元のIF、の2段階 → null判定＋早期return',
         '段落内のメッセージと呼出元のスキップ表示が1か所にまとまる。条件の向きは逆（原本は「登録あり」、Javaは「登録なし」を先に判定）。',
         ['card']),
    unit('xref-found', 'カード登録ありの表示', 'direct', [[234, 239]], [[118, 121]],
         'NOT INVALID KEY の DISPLAY×4 → println×4',
         '文言と順序は同じ。'),
    unit('account-read', '口座マスターの検索', 'replaced', [[174, 176], [241, 244]],
         [[53, 53], [80, 82], [85, 86], [90, 90], [123, 123]],
         'VSAMのキー読込 → 事前に作ったSetのcontains',
         '口座レコードは読まず、口座IDの集合に含まれるかだけを見る。索引と同じく事前読込に変わる。',
         ['account', 'master-timing']),
    unit('account-branch', '口座の有無による表示', 'restructured', [[177, 179], [245, 250]], [[123, 128]],
         'INVALID KEYの表示＋呼出元のIF → if／elseの1か所',
         '未登録時の2つのメッセージ（段落内と呼出元）がelse側に並ぶ。出力の順序は同じ。',
         ['account']),
    unit('close', '6ファイルを閉じる', 'consolidated', [[188, 193], [361, 467]], [[46, 46], [55, 55]],
         'CLOSE段落×6（各17行）→ try-with-resourcesの自動close',
         '113行が、tryブロックを抜ける1か所に集約される。閉じる順序は原本と逆。日次取引のCLOSE失敗時に顧客ファイルの文言と状態を表示する原本の記述（372〜373行）は再現していない。',
         ['close-order', 'daily-close-message']),
    unit('arguments', '起動引数の検査', 'added', [], [[28, 32]],
         '（由来なし）→ 引数の数を検査',
         'JCLのDD割当てに代わるデータフォルダーの指定を検査する。不足時は使い方を表示して終了コード2。',
         ['validation']),
    unit('width-check', 'レコード長の検査', 'added', [], [[68, 69], [83, 84], [96, 96], [98, 98], [131, 137]],
         '（由来なし）→ 行の長さを検査',
         '固定長ファイルでは起こらない長さの過不足を、テキスト入力に対して検査する。元環境で通るデータを拒否しないかは未確認。',
         ['validation']),
    unit('duplicate-check', 'キー重複の検査', 'added', [], [[72, 74], [86, 88]],
         '（由来なし）→ Map／Setへの登録時に重複を検査',
         'VSAMの主キー制約に当たる検査。登録（putIfAbsent／add）と同じ行で行う。',
         ['validation']),
]


def neutral(language, text):
    if language == 'cobol':
        return not text.strip() or text[6:7] in ('*', '/')
    return bool(re.fullmatch(r'\s*(//.*|import .*;|\}|@\w+\(.*\))?\s*', text))


def build():
    sources = {'cobol': (ROOT / 'original/CBTRN01C.cbl').read_bytes(),
               'java': (ROOT / 'DailyTransactionLookup.java').read_bytes()}
    for language, content in sources.items():
        assert sha256(content).hexdigest() == BASIS[language], language + ' changed; re-review the conversion ledger.'
    lines = {k: v.decode().splitlines() for k, v in sources.items()}
    review = json.loads((ROOT / 'review/review-model.json').read_text(encoding='utf-8'))
    review_ids = {c['id'] for c in review['comparisons']}
    kinds = {k for k, _, _ in KINDS}
    owners = {'cobol': {}, 'java': {}}
    assert len({u['id'] for u in UNITS}) == len(UNITS)
    for u in UNITS:
        assert u['kind'] in kinds and set(u['reviewIds']) <= review_ids, u['id']
        assert (u['kind'] == 'dropped') == (not u['newRanges']) and (u['kind'] == 'added') == (not u['oldRanges']), u['id']
        for language, key in (('cobol', 'oldRanges'), ('java', 'newRanges')):
            for start, end in u[key]:
                assert 1 <= start <= end <= len(lines[language]), (u['id'], start, end)
                for n in range(start, end + 1):
                    owners[language].setdefault(n, []).append(u['id'])
    # COBOL: an exact partition. Java: every line has an origin; several units may share a line.
    line_kinds = {}
    by_id = {u['id']: u for u in UNITS}
    for language in ('cobol', 'java'):
        result = []
        for n, text in enumerate(lines[language], 1):
            ids = owners[language].get(n, [])
            if language == 'cobol':
                assert len(ids) <= 1, ('COBOL line in two units', n, ids)
            if not ids:
                assert neutral(language, text), (language + ' line has no conversion unit', n, text)
            result.append(dict(units=ids, kind=by_id[ids[0]]['kind'] if ids else 'neutral'))
        line_kinds[language] = result
    counts = {language: {k: sum(row['kind'] == k for row in rows) for k in [*kinds, 'neutral']}
              for language, rows in line_kinds.items()}
    for u in UNITS:
        u['oldLines'] = sum(b - a + 1 for a, b in u['oldRanges'])
        u['newLines'] = sum(b - a + 1 for a, b in u['newRanges'])
    return dict(schemaVersion=1, basis=BASIS,
                limitation='Hand-reviewed correspondence for the pinned sources. It records where each line went and how; '
                           'it is not evidence that behaviour is equivalent.',
                kinds=[dict(id=k, label=label, description=text) for k, label, text in KINDS],
                totals=dict(cobol=len(lines['cobol']), java=len(lines['java'])), counts=counts,
                units=UNITS, lines=line_kinds)


if __name__ == '__main__':
    model = build()
    (ROOT / 'review/conversion-map.json').write_text(json.dumps(model, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    page = ROOT / 'viewer.html'
    html = page.read_text(encoding='utf-8')
    content = json.dumps(model, ensure_ascii=False, separators=(',', ':')).replace('<', r'<')
    element = '<script id="conversion-data" type="application/json">' + content + '</script>'
    if '<script id="conversion-data"' in html:
        html = re.sub(r'<script id="conversion-data".*?</script>', lambda _: element, html, count=1, flags=re.S)
    else:
        html = html.replace('<script id="verification-data"', element + '\n<script id="verification-data"', 1)
    page.write_bytes(html.encode('utf-8'))
    print(f'{len(model["units"])} conversion units saved.')
    for language in ('cobol', 'java'):
        print(language, model['totals'][language], model['counts'][language])
