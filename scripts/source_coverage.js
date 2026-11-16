// Source-order coverage component, embedded into the standalone viewer by sync_source_coverage.py.
// Classification and condition scope are limited to the constructs in this pinned example.
// Links reuse the existing graph ranges, decision bindings and definition inventory.
function buildSourceCoverage() {
  const raw=data.sources.cobol.split(/\r\n|\r|\n/);if(raw.at(-1)==="")raw.pop();
  const procedure=raw.findIndex(s=>s.slice(7,72).trim()==="PROCEDURE DIVISION.")+1;
  const files=review.mappings.filter(m=>m.category==="resource").map(m=>({dd:m.dd,file:m.oldName.split(" / ")[1]}));
  const names=new Map(review.mappings.filter(m=>m.category!=="resource"&&m.oldName!=="FILLER").map(m=>[m.oldName,m]));
  const flows=raw.map(()=>new Set());
  for(const trace of Object.values(traces))for(const step of trace)for(const [,a,b] of sourceRanges(step,"cobol"))
    for(let n=a;n<=b;n++)flows[n-1].add(step.block);
  const stack=[],issues=[],lines=[];
  let definitionDD=null,definitionMode=null,operation="",operationDD=[];
  const verbs=/^(MOVE|DISPLAY|READ|OPEN|CLOSE|PERFORM|ADD|CALL|GOBACK|CONTINUE|EXIT)\b/;
  for(let i=0;i<raw.length;i++) {
    const number=i+1,text=raw[i].slice(7,72).trim();
    const paragraph=audit.paragraphs.find(p=>number>=p.start&&number<=p.end);
    const own=audit.decisions.find(d=>number>=d.start&&number<=d.end);
    const comment=["*","/"].includes(raw[i][6]);
    const terms=new Set((text.replace(/'(?:''|[^'])*'|"(?:""|[^"])*"/g," ").match(/[A-Z][A-Z0-9-]*/g)||[]));
    const directDD=files.filter(f=>terms.has(f.file)||terms.has(f.dd)).map(f=>f.dd);
    const copy=Object.entries(layouts).find(([,v])=>text==="COPY "+v.copybook+".");
    let kind,statement="";
    if(!text)kind="blank";
    else if(comment)kind="comment";
    else if(number<=procedure) {
      kind=/(DIVISION|SECTION)\.$/.test(text)||/^(PROGRAM-ID|AUTHOR|FILE-CONTROL)\./.test(text)?"heading":"definition";
      if(/^SELECT\b/.test(text)){definitionDD=directDD[0]??null;definitionMode="select";}
      if(/^FD\b/.test(text)){definitionDD=directDD[0]??null;definitionMode="fd";}
      if(/^(WORKING-STORAGE|PROCEDURE)\b/.test(text)){definitionDD=null;definitionMode=null;}
      if(copy){definitionDD=null;definitionMode=null;}
    } else if(paragraph?.start===number) {
      kind="paragraph";
      if(stack.length)issues.push({line:number,reason:"段落開始時に未解決の条件スコープ"});
      stack.length=0;operation="";
    } else {
      if(/^ELSE\b/.test(text)) {
        if(stack.at(-1)?.type!=="if")issues.push({line:number,reason:"ELSEの対応先が未確定"});
        else stack.at(-1).branch="偽";
      }
      if(/^NOT INVALID KEY\b/.test(text)) {
        if(stack.at(-1)?.type!=="key")issues.push({line:number,reason:"NOT INVALID KEYの対応先が未確定"});
        else stack.at(-1).branch="偽（有効キー）";
      }
      if(own)kind="decision";
      else if(/^(ELSE|END-IF|END-READ|END-PERFORM|NOT INVALID KEY)\b/.test(text))kind="structure";
      else if(verbs.test(text)){kind="operation";statement=text.match(verbs)[1];operation=statement;operationDD=directDD;}
      else if(operation&&(/^(KEY IS|USING|OR |AND )/.test(text)||/^["']/.test(text)||names.has([...terms][0])))kind="continuation";
      else kind="unknown";
    }
    const required=number>procedure&&!["blank","comment"].includes(kind);
    const conditions=required?stack.filter(s=>s.line!==own?.start).map(s=>({line:s.line,branch:s.branch})):[];
    if(own)conditions.push({line:own.start,branch:"判定"});
    const dd=new Set(),fieldIds=[];
    if(!["blank","comment","heading"].includes(kind)) {
      directDD.forEach(v=>dd.add(v));
      if(kind==="definition"&&definitionDD)dd.add(definitionDD);
      if(copy)dd.add(copy[0]);
      if(kind==="continuation")operationDD.forEach(v=>dd.add(v));
      if(statement==="DISPLAY"||(kind==="continuation"&&operation==="DISPLAY"))dd.add("SYSOUT");
      if(own?.name==="INVALID KEY")dd.add(own.dd);
      for(const word of terms) {
        const field=names.get(word);
        if(field){fieldIds.push(field.id);if(layouts[field.dd])dd.add(field.dd);}
        const status=files.find(f=>word.startsWith(f.dd+"-STAT"));if(status)dd.add(status.dd);
      }
      const performed=text.match(/^PERFORM \d{4}-([A-Z]+)-(?:OPEN|CLOSE)/)?.[1];
      if(performed&&layouts[performed])dd.add(performed);
      if(/^PERFORM Z-DISPLAY-IO-STATUS/.test(text))dd.add("SYSOUT");
    }
    const conditionMissing=conditions.some(c=>!audit.decisions.find(d=>d.start===c.line)?.binding);
    const row={number,text,kind,statement,paragraph:paragraph?.name??null,flowIds:required?[...flows[i]]:[],
      conditions,ownDecision:own?.start??null,ioRefs:[...dd],fieldIds:[...new Set(fieldIds)],requiresFlow:required,
      missing:required&&(!flows[i].size||conditionMissing||kind==="unknown"),
      reason:kind==="comment"?"コメント。実行処理のフロー対応は不要。":kind==="blank"?"空行。処理や定義はありません。":
        kind==="heading"?"プログラムの宣言・区分。実行処理のフロー対応は不要。":kind==="definition"?"ファイル・データの定義。処理フローではなく、入出力・定義との対応を確認します。":
        kind==="unknown"?"この行の構文の種別は未判定です。原本を確認して分類・対応を補う必要があります。":
        !flows[i].size?"この行に対応するフロー範囲が未登録です。":conditionMissing?"フロー範囲には含まれますが、この行に関係する条件のケース対応には未登録があります。":
        "対応先へのリンクがあります。リンク先の処理・条件・項目がこのコードと合っているかを確認してください。"};
    lines.push(row);
    if(!comment&&kind!=="blank") {
      if(own?.start===number)stack.push({line:number,type:own.name.startsWith("IF ")?"if":own.name.startsWith("PERFORM")?"loop":"key",
        branch:own.name.startsWith("PERFORM")?"継続（偽）":own.name==="INVALID KEY"?"真（無効キー）":"真"});
      const closes=text.match(/^(END-IF|END-READ|END-PERFORM)\b/)?.[1];
      if(closes){const type={"END-IF":"if","END-READ":"key","END-PERFORM":"loop"}[closes];if(stack.at(-1)?.type===type)stack.pop();else issues.push({line:number,reason:closes+"の対応先が未確定"});}
      if(own||kind==="structure")operation="";
      if(number<=procedure&&definitionMode==="select"&&text.endsWith(".")){definitionDD=null;definitionMode=null;}
    }
  }
  if(stack.length)issues.push({line:raw.length,reason:"末尾で未解決の条件スコープ"});
  const ranges=[];
  for(const row of lines) {
    const signature=JSON.stringify([row.kind,row.flowIds,row.conditions,row.ownDecision,row.ioRefs,row.fieldIds,row.missing]);
    const previous=ranges.at(-1);
    if(previous&&previous.signature===signature&&previous.end-previous.start<7)previous.end=row.number;
    else ranges.push({...row,id:"source-"+row.number,start:row.number,end:row.number,signature});
  }
  const counts={total:lines.length,required:lines.filter(r=>r.requiresFlow).length,
    flowLinked:lines.filter(r=>r.requiresFlow&&r.flowIds.length).length,
    flowMissing:lines.filter(r=>r.requiresFlow&&!r.flowIds.length).length,
    definitions:lines.filter(r=>r.kind==="definition").length,
    neutral:lines.filter(r=>["comment","blank","heading"].includes(r.kind)).length,
    unknown:lines.filter(r=>r.kind==="unknown").length,decisions:audit.decisions.length,
    decisionsLinked:audit.decisions.filter(d=>d.binding).length};
  return {lines,ranges,counts,issues};
}
const sourceCoverage=buildSourceCoverage();
let sourceInspect=null;
let sourceReturnLine=null;
const sourceKindLabels={comment:"コメント",blank:"空行",heading:"宣言・区分",definition:"定義",paragraph:"段落の入口",operation:"実行文",decision:"判定式",structure:"分岐・反復の区切り",continuation:"文の続き",unknown:"未判定"};
const shortBlockLabels={open:"入力を開く",read:"読込",abort:"異常終了",display:"取引表示",eof:"EOF",xref:"カード照合",account:"口座照合",skip:"スキップ",found:"成功",missing:"口座未登録",loop:"終了判定",close:"閉じる"};
function visibleAuditItems() {
  return sourceCoverage.ranges.filter(r=>auditKind==="all"||auditKind==="process"&&r.requiresFlow||auditKind==="missing"&&r.missing||auditKind==="definitions"&&r.kind==="definition"||auditKind==="decisions"&&r.ownDecision);
}
function coverageRangeAt(line) {return sourceCoverage.ranges.find(r=>line>=r.start&&line<=r.end);}
function sourceLabel(item) {return "L"+item.start+(item.end===item.start?"":"–"+item.end);}
function sourceOriginBanner() {
  const bar=$("coverage-return");if(!bar)return;
  bar.hidden=sourceReturnLine===null||reviewStage!=="legacy"||detailView==="coverage";
  if(!bar.hidden)$("coverage-return-label").textContent="確認元：原本 L"+sourceReturnLine+" · "+(sourceInspect?"原本の条件・入出力を表示":"関連フローを表示");
}
function selectSourceLine(line) {
  const item=coverageRangeAt(Math.min(sourceCoverage.counts.total,Math.max(1,Math.floor(Number(line)||1))));
  if(!visibleAuditItems().some(r=>r.id===item.id)){auditKind="all";$("audit-kind").value="all";}
  auditSelected=item;
  if(detailView!=="coverage")changeDetail("coverage");else renderAudit();
}
function renderAudit() {
  const c=sourceCoverage.counts;
  $("audit-summary").replaceChildren(el("h3","原本 "+c.total+"行"),
    el("span","フロー未登録 "+c.flowMissing+"行","source-alert"),
    el("span","条件ケース未登録 "+(c.decisions-c.decisionsLinked)+" / "+c.decisions,"source-alert"));
  $("audit-denominators").textContent="対象はCBTRN01C本体の全"+c.total+"行。実行部 "+c.required+"行（段落・区切り含む）、定義 "+c.definitions+"行、コメント・空行・宣言 "+c.neutral+"行です。フロー未登録の分母は実行部、ケース未登録の分母は判定です。";
  $("audit-line").max=String(c.total);
  const items=visibleAuditItems(),body=$("audit-items");body.replaceChildren();
  $("audit-range-count").textContent=items.reduce((n,r)=>n+r.end-r.start+1,0)+"行を表示";
  const sourceLines=data.sources.cobol.split(/\r\n|\r|\n/);
  for(const item of items) {
    const row=el("tr");row.dataset.auditId=item.id;row.dataset.start=String(item.start);row.dataset.end=String(item.end);
    row.dataset.kind=item.kind;
    const cell=(label)=>{const td=el("td");if(label)td.dataset.label=label;row.append(td);return td;};
    const select=buttonLink(sourceLabel(item),()=>selectAuditItem(item));select.className="source-range-link";select.title=sourceKindLabels[item.kind];cell().append(select);
    const codeCell=cell();codeCell.className="source-code-cell";
    const code=el("pre",undefined,"source-inline-code");
    for(let n=item.start;n<=item.end;n++) {
      const line=el("span",undefined,"source-inline-line");line.dataset.sourceLine=String(n);
      const raw=sourceLines[n-1],body=raw.slice(7,72).trimEnd();
      if(["*","/"].includes(raw[6]))textToken(line,raw.slice(6,72).trimEnd(),"comment");
      else paintLine(line,body,"cobol");
      code.append(line);
    }
    codeCell.append(code);
    const flow=cell("フロー");
    if(item.flowIds.length){const id=item.flowIds[0];const b=buttonLink(shortBlockLabels[id],()=>{selectAuditItem(item);openSourceFlow(item,id);});b.dataset.flowLink=id;flow.append(b);
      if(item.flowIds.length>1){const more=buttonLink("+"+(item.flowIds.length-1),()=>{selectAuditItem(item);$("audit-selection").open=true;$("audit-detail").querySelector("details").open=true;revealSourceSelection();});more.title="ほかのフロー対応を表示";more.className="source-more";flow.append(more);}}
    else flow.append(el("span",item.requiresFlow?"未登録":"—",item.requiresFlow?"source-missing":"source-na"));
    const condition=cell("条件");
    if(item.conditions.length) {
      const linked=item.conditions.filter(s=>audit.decisions.find(d=>d.start===s.line)?.binding).length;
      const b=buttonLink(item.conditions.length+"条件",()=>{selectAuditItem(item);openSourceInspector(item,"condition");});
      if(linked<item.conditions.length)b.append(el("span","未登録"+(item.conditions.length-linked),"source-gap-count"));
      b.className=linked<item.conditions.length?"source-partial":"";b.title="この行に関係する条件とケース対応の未登録数";b.dataset.conditionLink="true";condition.append(b);
    } else condition.append(el("span","—","source-na"));
    const io=cell("入出力");
    if(item.ioRefs.length||item.fieldIds.length) {
      const label=item.ioRefs.length?(item.ioRefs[0]==="SYSOUT"?"表示出力":item.ioRefs[0]):"変数定義";
      const b=buttonLink(label+(item.ioRefs.length>1?" +"+(item.ioRefs.length-1):""),()=>{selectAuditItem(item);openSourceInspector(item,"io");});b.dataset.ioLink="true";io.append(b);
    } else io.append(el("span","—","source-na"));
    row.addEventListener("click",e=>{if(!e.target.closest("button"))selectAuditItem(item);});body.append(row);
  }
  const selected=items.find(i=>i.id===auditSelected?.id)??items[0];
  if(selected)selectAuditItem(selected);else emptyReview($("audit-detail"));
  sourceOriginBanner();
}
function selectAuditItem(item) {
  auditSelected=item;
  for(const row of $("audit-items").querySelectorAll("tr"))row.setAttribute("aria-selected",String(row.dataset.auditId===item.id));
  setPaneRanges(panes.cobol,[["原本の範囲",item.start,item.end]]);setPaneRanges(panes.java,[]);
  $("audit-line").value=String(item.start);
  const detail=$("audit-detail");detail.replaceChildren(el("h3",sourceLabel(item)+" · "+sourceKindLabels[item.kind]),el("p",item.reason));
  const related=el("details",undefined,"source-range-details");
  related.append(el("summary","この範囲の条件・対応先を表示"));
  if(item.conditions.length) {
    const list=el("ul",undefined,"source-condition-path");
    for(const context of item.conditions){const d=audit.decisions.find(d=>d.start===context.line);list.append(el("li","L"+d.start+" "+d.name+" → "+context.branch));}
    related.append(list);
  }
  const links=el("div",undefined,"review-relations");
  for(const id of item.flowIds)links.append(buttonLink("フロー："+blocks[id].label,()=>openSourceFlow(item,id)));
  if(item.conditions.length)links.append(buttonLink("条件との対応を見る",()=>openSourceInspector(item,"condition")));
  if(item.ioRefs.length||item.fieldIds.length)links.append(buttonLink("入出力・定義との対応を見る",()=>openSourceInspector(item,"io")));
  if(item.requiresFlow&&!item.flowIds.length) {
    const related=item.paragraph?.endsWith("-OPEN")?"open":item.paragraph?.endsWith("-CLOSE")?"close":null;
    if(related){links.prepend(el("p","要約図には「"+blocks[related].label+"」がありますが、この行への登録はありません。","source-warning"));links.append(buttonLink("未登録のまま、関連する要約図を見る",()=>openSourceFlow(item,related)));}
  }
  related.append(links);
  if(item.conditions.length||links.childElementCount)detail.append(related);
  sourceWalkFooter(item);
  revealSourceSelection();
}
function revealSourceSelection() {
  const row=$("audit-items").querySelector('[aria-selected="true"]'),list=$("audit-table-scroll");
  if(row){const a=row.getBoundingClientRect(),b=list.getBoundingClientRect(),h=list.querySelector("thead").getBoundingClientRect().height;if(a.top<b.top+h)list.scrollTop+=a.top-b.top-h-3;else if(a.bottom>b.bottom)list.scrollTop+=a.bottom-b.bottom+3;}
}
function sourceWalkFooter(item) {
  const items=visibleAuditItems(),at=items.findIndex(r=>r.id===item.id);
  $("step-count").textContent="原本 "+sourceLabel(item)+" / "+sourceCoverage.counts.total+"行";
  $("step-name").textContent=sourceKindLabels[item.kind];$("step-context").textContent=item.missing?"対応を補う必要あり":"";
  $("description").textContent="右側の対応先を開いて確認。前へ・次へで原本を順に辿れます。";
  $("decision-link").hidden=true;$("prev").disabled=at<=0;$("next").disabled=at<0||at===items.length-1;
  if($("audit-selection-label"))$("audit-selection-label").textContent=sourceLabel(item)+" の説明・すべての対応先";
}
function openSourceFlow(item,id) {
  sourceReturnLine=item.start;changeDetail("flow");jumpToBlock(id);sourceOriginBanner();fitGraph();
}
function openSourceInspector(item,section) {
  sourceReturnLine=item.start;changeDetail("io",{item,section});
}
function showSourceCase(item,decision,caseId,value) {
  sourceReturnLine=item.start;scenario=caseId;
  index=traces[caseId].findIndex(s=>decision.binding.nodes.includes(s.block)&&decision.binding.value(s)===value);
  changeDetail("flow");sourceOriginBanner();fitGraph();
}
function renderSourceInspector(origin) {
  const item=origin.item,panel=$("inspector");
  setPaneRanges(panes.cobol,[["確認元の範囲",item.start,item.end]]);setPaneRanges(panes.java,[]);
  panel.replaceChildren(el("h3",sourceLabel(item)+" の"+(origin.section==="condition"?"条件との対応":"入出力・定義との対応")),el("p",item.reason));
  panel.append(el("pre",sourceCoverage.lines.slice(item.start-1,item.end).map(r=>"L"+r.number+" "+r.text).join("\n"),"source-excerpt"));
  if(origin.section==="condition") {
    for(const context of item.conditions) {
      const d=audit.decisions.find(d=>d.start===context.line),card=el("section",undefined,"source-condition-card");
      card.append(el("h4","L"+d.start+" · "+context.branch),el("code",d.name));
      if(d.binding) {
        card.append(el("p","対応するフロー："+blocks[d.binding.block].label));
        const links=el("div",undefined,"review-relations");links.append(buttonLink("対応するフローを開く",()=>openSourceFlow(item,d.binding.block)));
        for(const [key,label] of [["true","真"],["false","偽"]]) {
          card.append(el("p",label+"のモデルケース："+(d.outcomes[key].map(id=>caseNames[id]).join("、")||"未登録")));
          const id=d.outcomes[key][0];if(id)links.append(buttonLink(label+"の例を辿る",()=>showSourceCase(item,d,id,key==="true")));
        }
        card.append(links);
      } else card.append(el("p","この判定とフロー／モデルケースの対応は未登録です。条件式の表示だけでは確認済みになりません。","source-warning"));
      panel.append(card);
    }
    panel.append(el("p","条件の所属・真偽側は、この原本のIF／ELSE／END-IF等から追った構造です。ケースの真偽は再構成モデルで、COBOL実行による計測ではありません。","source-note"));
  } else {
    for(const dd of item.ioRefs) {
      const section=el("section",undefined,"source-condition-card");
      section.append(el("h4",dd==="SYSOUT"?"SYSOUT · DISPLAYの表示出力":dd+" · "+layouts[dd].title));
      if(dd!=="SYSOUT")section.append(el("p",layouts[dd].access+" / "+layouts[dd].record+" / "+layouts[dd].width+"桁"),el("p",layouts[dd].key?"主キー："+layouts[dd].key:"順次入力。キー検索の定義なし。"));
      else section.append(el("p","原本のDISPLAYによる出力。具体的な文言・項目は上の確認元コードで照合します。"));
      section.append(buttonLink(dd==="SYSOUT"?"出力の定義を開く":"レコード全項目の定義を開く",()=>openDictionary(dd)));
      panel.append(section);
    }
    if(item.fieldIds.length) {
      panel.append(el("h4","この範囲に現れる項目"));
      const records=item.fieldIds.map(id=>{const f=review.mappings.find(m=>m.id===id);return [f.oldName,f.oldType,f.definition?f.definition.copybook+" / "+f.definition.position.join("–")+"桁":"WORKING-STORAGE L"+f.oldRanges[0][0]];});
      panel.append(definitionTable(["原本の項目名","定義","定義の根拠"],records));
    }
    panel.append(el("p","入出力のリンクはソースのファイル名・COPY句・参照項目から結んでいます。定義を開けることと、I/O処理や異常系がフローで説明済みであることは別です。","source-note"));
    if(item.flowIds.length) {
      const links=el("div",undefined,"review-relations");for(const id of item.flowIds)links.append(buttonLink("フロー："+blocks[id].label,()=>openSourceFlow(item,id)));panel.append(links);
    } else if(item.requiresFlow)panel.append(el("p","この行のフロー範囲は未登録です。","source-warning"));
  }
  panel.scrollTop=0;sourceWalkFooter(item);sourceOriginBanner();
}
function nextMissingSourceRange() {
  const items=sourceCoverage.ranges.filter(r=>r.missing),start=auditSelected?.start??0;
  const next=items.find(r=>r.start>start)??items[0];if(next)selectSourceLine(next.start);
}
