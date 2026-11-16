/* バッチ設計ビューワー共通の部品。各テンプレートは VIEWS・R・goSel・afterRender・chipLabel を定義してから startApp() を呼ぶ。 */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sp = (k) => { const i = k.indexOf(":"); return [k.slice(0, i), k.slice(i + 1)]; };
const isComment = (t) => t.length > 6 && (t[6] === "*" || t[6] === "/");
const mergeLines = (ls) => ls.reduce((acc, i) => { const last = acc[acc.length - 1]; if (last && i === last[1] + 1) last[1] = i; else acc.push([i, i]); return acc; }, []);
const pill = (cls, text) => `<span class="pill ${cls}">${esc(text)}</span>`;

/* ソースの抜粋。kind が "cobol" なら1〜6桁目（連番）を省いて表示する */
function srcBlock(lines, ranges, hl = [], kind = "cobol") {
  const hlset = new Set();
  hl.forEach(([a, b]) => { for (let i = a; i <= b; i++) hlset.add(i); });
  let out = "";
  ranges.forEach(([a, b], k) => {
    if (k) out += `<span class="src-gap">⋮</span>`;
    for (let i = Math.max(1, a); i <= Math.min(lines.length, b); i++) {
      const t = (lines[i - 1] || "").replace(/\s+$/, "");
      const body = kind === "cobol" ? t.slice(6) : t;
      const cm = kind === "cobol" ? isComment(t) : t.startsWith("//*");
      out += `<span class="ln${cm ? " cm" : ""}"${hlset.has(i) ? ' style="background:var(--hl)"' : ""}><span class="no">${i}</span>${esc(body || " ")}</span>`;
    }
  });
  return `<pre class="src">${out}</pre>`;
}

/* つながり欄。rows は [見出し, キーの配列] */
function chips(keys, max = 8) {
  const one = (k) => `<button class="chip" data-go="${esc(k)}">${esc(chipLabel(k))}</button>`;
  let h = keys.slice(0, max).map(one).join("");
  if (keys.length > max) h += `<details class="more"><summary>ほか${keys.length - max}件</summary>${keys.slice(max).map(one).join("")}</details>`;
  return h;
}
function relBox(rows) {
  return `<div class="rel"><b class="rh">つながり</b>${rows.map(([lab, ks]) => `<div class="relrow"><span class="rl">${esc(lab)}</span><div class="chips">${ks.length ? chips(ks) : '<span class="none">なし</span>'}</div></div>`).join("")}</div>`;
}

/* DFD。D = { width, height, nodes: [{key, shape:"circle"|"rect"|"store", x, y, w, h, title, lines, sub, no, cls}], flows: [{key, from, to, label, cls, offset, la, lo}] } */
function dfdSvg(D, selKey) {
  const byKey = Object.fromEntries(D.nodes.map(n => [n.key, n]));
  const on = new Set(), near = new Set();
  const [st] = sp(selKey);
  D.flows.forEach(f => { if (st === "F" ? f.key === selKey : (f.from === selKey || f.to === selKey)) { on.add(f.key); near.add(f.from); near.add(f.to); } });
  const clip = (n, tx, ty) => {
    const dx = tx - n.x, dy = ty - n.y, len = Math.hypot(dx, dy) || 1;
    if (n.shape === "circle") return [n.x + dx / len * n.r, n.y + dy / len * n.r];
    const k = Math.min(n.w / 2 / Math.abs(dx || 1e-9), n.h / 2 / Math.abs(dy || 1e-9));
    return [n.x + dx * k, n.y + dy * k];
  };
  let s = `<svg class="dfd" viewBox="0 0 ${D.width} ${D.height}" style="width:100%;min-width:${Math.min(D.width, D.minWidth || 660)}px;max-width:${D.width}px;height:auto;display:block" role="img" aria-label="DFD">
  <defs>${["dah", "dah-on"].map(m => `<marker id="${m}" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto"><path d="M0,0 L10,5 L0,10 z" style="fill:var(${m === "dah" ? "--muted" : "--accent"})"/></marker>`).join("")}</defs>`;
  D.flows.forEach(f => {
    const a = byKey[f.from], b = byKey[f.to];
    let p1 = clip(a, b.x, b.y), p2 = clip(b, a.x, a.y);
    if (f.offset) {
      const dx = p2[0] - p1[0], dy = p2[1] - p1[1], len = Math.hypot(dx, dy) || 1, ox = -dy / len * f.offset, oy = dx / len * f.offset;
      p1 = [p1[0] + ox, p1[1] + oy]; p2 = [p2[0] + ox, p2[1] + oy];
    }
    const t = f.lt ?? 0.5;
    const mx = p1[0] + (p2[0] - p1[0]) * t + (f.lo?.[0] || 0), my = p1[1] + (p2[1] - p1[1]) * t + (f.lo?.[1] || 0), o = on.has(f.key);
    const ln = `x1="${p1[0]}" y1="${p1[1]}" x2="${p2[0]}" y2="${p2[1]}"`;
    s += `<g data-k="${f.key}" class="flow ${o ? "on" : ""} ${f.key === selKey ? "sel" : ""}"><line class="hit" ${ln}/><line class="fl ${f.cls || ""}" ${ln} marker-end="url(#${o ? "dah-on" : "dah"})"/>
      ${f.label ? `<text class="flab" x="${mx}" y="${my}" text-anchor="${f.la || "middle"}">${esc(f.label)}</text>` : ""}</g>`;
  });
  D.nodes.forEach(n => {
    const cls = `${n.cls || ""} ${n.key === selKey ? "sel" : near.has(n.key) ? "rel" : ""}`;
    if (n.shape === "circle") {
      s += `<g data-k="${n.key}" class="proc ${cls}"><circle class="shape" cx="${n.x}" cy="${n.y}" r="${n.r}"/>
        <text class="sub" x="${n.x}" y="${n.y - 24}" text-anchor="middle">${esc(n.no)}</text>
        ${n.lines.map((l, i) => `<text x="${n.x}" y="${n.y - 2 + i * 18 - (n.lines.length - 2) * 9}" text-anchor="middle" font-size="13" font-weight="500">${esc(l)}</text>`).join("")}
        ${n.sub ? `<text class="sub" x="${n.x}" y="${n.y + 34}" text-anchor="middle">${esc(n.sub)}</text>` : ""}</g>`;
    } else if (n.shape === "rect") {
      s += `<g data-k="${n.key}" class="ext ${cls}"><rect class="shape" x="${n.x - n.w / 2}" y="${n.y - n.h / 2}" width="${n.w}" height="${n.h}"/>
        <text x="${n.x}" y="${n.y - 4}" text-anchor="middle" font-size="13" font-weight="500">${esc(n.no + " " + n.title)}</text>
        <text class="sub" x="${n.x}" y="${n.y + 13}" text-anchor="middle">${esc(n.sub || "")}</text></g>`;
    } else {
      const x = n.x - n.w / 2, y = n.y - 22, w = n.w;
      s += `<g data-k="${n.key}" class="store ${cls}"><rect class="bg" x="${x}" y="${y}" width="${w}" height="44"/>
        <line class="sl" x1="${x}" y1="${y}" x2="${x + w}" y2="${y}"/><line class="sl" x1="${x}" y1="${y + 44}" x2="${x + w}" y2="${y + 44}"/>
        <line class="sl" x1="${x}" y1="${y}" x2="${x}" y2="${y + 44}"/><line class="sl" x1="${x + 36}" y1="${y}" x2="${x + 36}" y2="${y + 44}"/>
        <text x="${x + 18}" y="${y + 27}" text-anchor="middle" font-size="12.5" font-weight="500">${esc(n.no)}</text>
        <text x="${x + 46}" y="${y + 20}" font-size="12.5" font-weight="500">${esc(n.title)}</text>
        <text class="sub" x="${x + 46}" y="${y + 35}">${esc(n.sub || "")}</text></g>`;
    }
  });
  return s + `</svg>`;
}

/* レコードレイアウトの帯 */
function layoutBar(fields, len, name, useCls) {
  const sc = 600 / len;
  let bar = `<svg class="lay" viewBox="0 0 600 40" style="width:100%;height:auto;display:block" role="img" aria-label="${esc(name)}のレコードレイアウト">`;
  fields.forEach(f => {
    bar += `<rect class="${useCls(f)}" x="${(f.pos[0] - 1) * sc}" y="4" width="${Math.max((f.pos[1] - f.pos[0] + 1) * sc, 1)}" height="22" data-go="I:${f.item}"><title>${f.pos[0]}–${f.pos[1]} ${esc(f.name)}（${esc(f.meaning)}）</title></rect>`;
  });
  return bar + `<text class="sub" x="0" y="38">1</text><text class="sub" x="600" y="38" text-anchor="end">${len}バイト</text></svg>`;
}

/* 画面の切替 */
function render() {
  $("#rail").innerHTML = VIEWS.map((v, i) => `<li><button data-v="${v.id}" aria-current="${v.id === state.view}"><span class="n">${i + 1}</span><span class="t">${esc(v.t)}</span><span class="d">${esc(v.d)}</span></button></li>`).join("");
  $("#main").innerHTML = R[state.view]();
  afterRender();
}
function show(v) {
  state.view = v;
  if (location.hash !== "#" + v) history.replaceState(null, "", "#" + v);
  render();
  window.scrollTo({ top: 0 });
}
function startApp() {
  document.addEventListener("click", e => {
    const g = e.target.closest("[data-go]"); if (g) { goSel(g.dataset.go); return; }
    const b = e.target.closest("[data-v]"); if (b) show(b.dataset.v);
  });
  window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (R[v] && v !== state.view) { state.view = v; render(); } });
  const v = location.hash.slice(1); if (R[v]) state.view = v;
  render();
}
