"""Build the reviewed CardDemo example ledger. This is not a general COBOL parser.

Source hashes pin the line-level review. Changed sources require re-reviewing this
ledger, not just updating a hash or extending a highlighted range.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def build():
    old = (ROOT / 'original/CBTRN01C.cbl').read_bytes()
    new = (ROOT / 'DailyTransactionLookup.java').read_bytes()
    expected = {'cobol': '55c2aebd59528aa42b28878ba5ca4d17a00b3548fc25e4ce1529710d366fd576',
                'java': 'c24845f18a0f1a8db729904eea75749d43a67d8380f38e468b4279b2326277a3'}
    assert sha256(old).hexdigest() == expected['cobol'], 'Original changed; re-review the source mappings.'
    assert sha256(new).hexdigest() == expected['java'], 'Java changed; re-review the source mappings.'
    source = old.decode().splitlines()
    html = (ROOT / 'viewer.html').read_text(encoding='utf-8')
    layouts = json.loads(re.search(r'<script type="application/json" id="layouts">(.*?)</script>', html, re.S)[1])

    def behavior(id, title, kind, old_ranges, new_ranges, before, after, conclusion, next_action,
                 block, cases=(), fields=()):
        return dict(id=id, title=title, kind=kind, oldRanges=old_ranges, newRanges=new_ranges,
                    before=before, after=after, conclusion=conclusion, nextAction=next_action,
                    legacyBlock=block, caseIds=list(cases), fieldNames=list(fields), disposition='unreviewed')

    comparisons = [
        behavior('open', '6入力を開く', 'mapped', [[157,162],[252,268]], [[44,51],[59,61]],
            '日次取引、顧客、索引、カード、口座、既存取引をこの順でOPEN INPUT。',
            '同じ6入力を同じ順で開き、ASCIIとして読む。',
            '開く対象と順序に対応あり。VSAMからローカルファイルへの置換と、途中失敗時の解放方式は別途確認が必要。',
            '各ファイルのOPEN失敗を発生させ、終了状態・解放状態を旧環境と突合する。', 'open'),
        behavior('read', '日次取引の読込・表示', 'mapped', [[164,169],[202,217]], [[93,101]],
            'READ成功で350桁の作業レコードをDISPLAY。状態00・10・その他で分岐。',
            'readLine成功で350桁に空白補完して表示。nullでEOF、IOExceptionでエラー。',
            '通常入力のログは処理モデルとJavaで照合済み。省略可能な行末や文字コードは入力変換の前提。',
            '旧環境と同じ論理レコードで、通常・EOF・I/Oエラーを比較する。', 'read', ['sample','success'], ['DALYTRAN-ID','DALYTRAN-CARD-NUM']),
        behavior('eof', 'EOF後の再照合・空入力', 'assumption', [[164,186],[203,225]], [[95,105]],
            'EOFのガードは取引の表示にだけ適用。照合はその後も実行する。',
            'ループ後にもう一度照合。0件の場合の作業領域は空白350桁で初期化。',
            '最終レコードの再照合は維持。空入力時のCOBOL作業領域の初期値はランタイムを含め未確認。',
            'COBOL実行環境で0件・1件入力を実行し、初期値と最終照合ログを確認する。', 'eof', ['empty','success'], ['END-OF-DAILY-TRANS-FILE','DALYTRAN-CARD-NUM']),
        behavior('card', 'カード番号の照合', 'mapped', [[170,184],[227,239]], [[108,121]],
            'WS-XREF-READ-STATUS = 0 のとき登録あり。未登録は4を設定してスキップ表示。',
            'reference == null のとき未登録。登録があれば口座ID・顧客IDを取得。',
            '条件式の真偽は逆だが、登録あり／なしの行き先は対応している。これはソース上の比較結果。',
            'キー欠落・先頭ゼロを含むデータで新旧の出力を比較する。', 'xref', ['success','noCard'], ['DALYTRAN-CARD-NUM','XREF-CARD-NUM','XREF-CUST-ID','XREF-ACCT-ID','WS-XREF-READ-STATUS']),
        behavior('account', '口座IDの存在確認', 'mapped', [[173,179],[241,250]], [[123,128]],
            '口座をREAD。WS-ACCT-READ-STATUS NOT = 0 なら未登録を表示。',
            'accountIds.contains(...) が真なら成功、偽なら未登録を表示。',
            '口座の有無による分岐とログの対応あり。取得タイミングとデータ構造の差は別項目で扱う。',
            '登録あり／なしの入力を旧環境でも実行し、出力を突合する。', 'account', ['success','noAccount'], ['XREF-ACCT-ID','ACCT-ID','WS-ACCT-READ-STATUS']),
        behavior('master-timing', 'マスターを読むタイミング', 'difference', [[229,230],[243,244]], [[52,54],[64,91]],
            '取引の処理中にVSAMをキー検索する。',
            '取引処理の前にマスター全体をMap／Setへ読み込む。',
            '読込時点、使用メモリ、異常を検知する時点が変わる。同時更新がある場合の見え方も検討が必要。',
            'バッチ中のマスター更新有無、スナップショット要件、件数上限を決める。', 'xref', [], ['XREF-CARD-NUM','ACCT-ID']),
        behavior('close-order', '終了時のCLOSE順序', 'difference', [[188,197]], [[46,56]],
            'OPENと同じ順に日次取引→顧客→索引→カード→口座→既存取引を閉じる。',
            'try-with-resourcesで宣言の逆順に閉じる。途中に例外があっても他の資源のcloseを試みる。',
            '正常時の終了ログが同じでも、CLOSEの順序と失敗時の解放方式は異なる。',
            'CLOSE順序・例外連鎖・ジョブ終了条件の要件を確認し、維持か変更かを判断する。', 'close'),
        behavior('errors', '状態表示と異常終了', 'difference', [[219,222],[469,489]], [[35,38]],
            'FILE STATUSを整形してDISPLAYし、ABCODE 999でCEE3ABDを呼ぶ。',
            '例外メッセージを標準エラーへ表示し、プロセス終了コード1を返す。',
            '診断文、出力先、状態コードの表現が変わる。運用監視やジョブ制御との契約を未確認。',
            '監視ルール・終了コード・ログ仕様を確認し、エラーケースを新旧で突合する。', 'abort', [], ['IO-STATUS','ABCODE']),
        behavior('daily-close-message', '日次取引CLOSE失敗時の診断', 'difference', [[361,376]], [[35,38],[55,55]],
            'DALYTRANのCLOSE失敗処理が、CUSTOMER FILEの文言とCUSTFILE-STATUSを参照している。',
            '失敗したJavaのI/O例外を表示する。COBOLと同じ別ファイルの状態表示は再現していない。',
            '原本にある不整合の候補。移行時に修正してよいかは未決定。',
            '原本の不具合を維持するか、修正差分として扱うかをレビューする。', 'close', [], ['DALYTRAN-STATUS','CUSTFILE-STATUS']),
        behavior('validation', 'Javaで追加した入力検査', 'added', [], [[28,31],[69,74],[85,88],[131,137]],
            'CLI引数・ASCII行長・メモリ上の索引重複を検査する同じ文はない。VSAM側の制約との関係は別途確認。',
            '引数不足、カード／口座キーの重複、レコード長の異常を明示的に検出。',
            'Java側の4検査は実行済み。元環境で受理されるデータを新たに拒否しないかは未確認。',
            '旧データの制約と入力変換仕様に照らし、追加検査の許容範囲を決める。', None,
            ['arguments','duplicate-card','duplicate-account','record-width'])
    ]
    line = lambda text: next(i+1 for i,s in enumerate(source) if text in s)
    copies = {dd: line('COPY '+v['copybook']+'.') for dd,v in layouts.items()}
    files = {'DALYTRAN':('DALYTRAN-FILE',46),'CUSTFILE':('CUSTOMER-FILE',47),'XREFFILE':('XREF-FILE',48),
             'CARDFILE':('CARD-FILE',49),'ACCTFILE':('ACCOUNT-FILE',50),'TRANFILE':('TRANSACT-FILE',51)}
    direct = {
        'DALYTRAN-ID': ('transaction.substring(0, TRANSACTION_ID_LENGTH)', [[181,183]], [[114,116]]),
        'DALYTRAN-CARD-NUM': ('card', [[170,172]], [[110,112]]),
        'XREF-CARD-NUM': ('byCard のキー / card', [[228,230]], [[70,72],[110,112]]),
        'XREF-CUST-ID': ('CrossReference.customerId()', [[238,238]], [[71,71],[121,121]]),
        'XREF-ACCT-ID': ('CrossReference.accountId()', [[175,176],[237,237]], [[71,71],[120,123]]),
        'ACCT-ID': ('accountIds の要素 / reference.accountId()', [[242,244]], [[85,86],[123,123]])
    }
    mappings = []
    for dd, layout in layouts.items():
        for name, meaning, pic, start, end in layout['fields']:
            old_ranges = [[copies[dd], copies[dd]]]
            if name in direct:
                target, uses, new_ranges = direct[name]
                old_ranges += uses
                kind, new_type = 'direct', 'String（IDの先頭ゼロを保持）'
                rule = '固定幅の部分文字列を文字列のまま使用。PICが数値でもIDを数値演算へ変換しない。'
            elif dd == 'DALYTRAN':
                target, new_ranges, kind, new_type = 'current（350桁レコード内）', [[95,100]], 'aggregate', 'String内の部分領域'
                old_ranges += [[168,168]]
                rule = '個別のJava変数には分割せず、レコード全体として保持・表示。金額や日時の型変換を検証したことにはならない。'
            elif dd in ('ACCTFILE','XREFFILE'):
                target, new_ranges, kind, new_type = '個別の保持先なし', [], 'not-used', '—'
                rule = 'このバッチでは個別参照なし。Javaの索引では保持しない。他プログラムでの利用は今回の調査範囲外。'
            else:
                target, new_ranges, kind, new_type = 'ファイル単位のOPEN／CLOSEのみ', [], 'resource-only', '—'
                rule = '原本・Javaとも、このバッチではレコード項目を使用しない。ファイル対応と項目対応を区別する。'
            mappings.append(dict(id=f'field:{dd}:{start}:{name}', category='field', dd=dd, oldName=name, meaning=meaning,
                oldType='PIC '+pic, newName=target, newType=new_type, kind=kind, rule=rule,
                oldRanges=old_ranges, newRanges=new_ranges,
                definition=dict(copybook=layout['copybook'], record=layout['record'], position=[start,end], pic=pic),
                disposition='unreviewed'))

    control = {
        'END-OF-DAILY-TRANS-FILE':('readLine() のnull判定とループ後の再照合',[[97,105]],'transformed','EOFフラグを制御構造へ置換。空入力時の初期値は要確認。'),
        'WS-XREF-READ-STATUS':('reference == null',[[111,116]],'transformed','0／4の状態を参照の有無へ置換。条件の真偽の向きに注意。'),
        'WS-ACCT-READ-STATUS':('accountIds.contains(...)',[[123,127]],'transformed','0／4の状態を存在判定へ置換。'),
        'APPL-RESULT':('通常経路／EOF／IOException',[[97,105],[35,38]],'transformed','0・16・その他の状態表現をループと例外へ置換。'),
        'APPL-AOK':('通常の制御経路',[[97,101],[35,38]],'transformed','88レベルの条件名に直接対応する変数は設けていない。'),
        'APPL-EOF':('readLine() == null',[[97,105]],'transformed','88レベルのEOF条件をnull判定へ置換。'),
        'ABCODE':('System.exit(1)',[[35,38]],'transformed','999をメッセージに残すが、プロセス終了コードは1。運用上の意味の差は未承認。'),
        'TIMING':('対応する値なし',[],'unmapped','CEE3ABDの引数をJavaでは再現していない。'),
    }
    for i, text in enumerate(source[:153]):
        if i < 99 or text[6:7] in ('*','/'):
            continue
        match = re.match(r'\s*(01|05|88)\s+([A-Z][A-Z0-9-]+)(.*)',text)
        if not match:
            continue
        level,name,decl=match.groups()
        if name in control:
            target,new_ranges,kind,rule=control[name]
        elif name in {dd+'-STATUS' for dd in files}:
            target,new_ranges,kind,rule='I/Oの戻り値・IOException',[[35,38]],'transformed','ファイル状態の2桁を保持せず、JavaのI/O結果と例外へ置換。診断形式は差分として確認する。'
        else:
            target,new_ranges,kind,rule='個別の対応は未整理',[],'unmapped','状態コードの構成要素・表示用領域・グループを含む。対応が未整理の項目を未登録のまま残す。'
        mappings.append(dict(id='variable:'+name, category='variable',dd='WORKING-STORAGE',oldName=name,
            meaning='制御・作業領域',oldType=(decl.strip() or 'グループ項目').rstrip('.'),newName=target,
            newType='制御構造／例外' if new_ranges else '—',kind=kind,rule=rule,
            oldRanges=[[i+1,i+1]],newRanges=new_ranges,disposition='unreviewed'))

    for dd,(filename,jline) in files.items():
        opened,closed=line('OPEN INPUT '+filename),line('CLOSE '+filename)
        layout=layouts[dd]
        target = {'XREFFILE':'cardxref.txt → Map<String, CrossReference>', 'ACCTFILE':'acctdata.txt → Set<String>'}.get(dd,layout['filename'])
        mappings.append(dict(id='resource:'+dd,category='resource',dd=dd,oldName=dd+' / '+filename,
            meaning=layout['title'],oldType=layout['access'],newName=target,newType='ASCIIテキスト入力',kind='transformed',
            rule='この例にSQLテーブル・列はない。VSAM／固定長入力からローカルASCIIへのI/F置換。文字コード変換、排他、更新タイミングは別途検証が必要。',
            oldRanges=[[opened,opened],[closed,closed]],newRanges=[[jline,jline],[59,61]],disposition='unreviewed'))
    for c in comparisons:
        names=c.pop('fieldNames')
        c['mappingIds']=[m['id'] for m in mappings if m['oldName'] in names]
    for m in mappings:
        m['behaviorIds']=[c['id'] for c in comparisons if m['id'] in c['mappingIds']]
    return dict(schemaVersion=1, basis=expected, purpose='移行前後の処理・データの対応と差分を確認する',
        scope=dict(old='original/CBTRN01C.cbl',new='DailyTransactionLookup.java',
            revision='59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e',
            definitions='既存ビューアーに収録した固定版COPY句の抽出定義。COPY句の全文は未同梱。',
            runtimeComparison='not-run',approval='unreviewed'), comparisons=comparisons,mappings=mappings)


if __name__ == '__main__':
    model=build()
    target=ROOT/'review'/'review-model.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    page=ROOT/'viewer.html'
    html=page.read_text(encoding='utf-8')
    content=json.dumps(model,ensure_ascii=False,separators=(',',':')).replace('<',r'\u003c')
    element='<script id="review-data" type="application/json">'+content+'</script>'
    if '<script id="review-data"' in html:
        html=re.sub(r'<script id="review-data".*?</script>',lambda _:element,html,count=1,flags=re.S)
    else:
        html=html.replace('<script id="verification-data"',element+'\n<script id="verification-data"',1)
    page.write_bytes(html.encode())
    print(f'{len(model["comparisons"])} behavior reviews, {len(model["mappings"])} data mappings saved.')
