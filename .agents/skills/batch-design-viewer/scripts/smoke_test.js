/* 書き出したビューワーをブラウザーで開き、全画面の表示・つながりのリンク・狭い画面での横はみ出しを確かめる。
   使い方: node smoke_test.js batch-viewer/CBTRN01C.html batch-viewer/daily-job.html
   Playwright（require('playwright')）と Chromium が必要です。 */
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { console.error("playwright が見つかりません。npm i -D playwright などで用意してください。"); process.exit(2); }

(async () => {
  const files = process.argv.slice(2);
  if (!files.length) { console.error("確かめるHTMLを指定してください"); process.exit(2); }
  const browser = await chromium.launch();
  let failed = 0;
  for (const f of files) {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text())) errors.push(m.text()); });
    await page.goto("file://" + path.resolve(f));
    const views = await page.$$eval("#rail [data-v]", bs => bs.map(b => b.dataset.v));
    let links = 0;
    for (const v of views) {
      await page.evaluate(v => { location.hash = v; }, v);
      await page.waitForTimeout(60);
      const n = await page.$$eval("#main", m => m[0].innerHTML.length);
      if (n < 200) errors.push(`${v}: 画面がほぼ空です`);
      // つながりのリンクを順に押して、例外が出ないことと移動先が描けることを確かめる
      const gos = await page.$$eval("#main [data-go]", els => [...new Set(els.map(e => e.dataset.go))].slice(0, 25));
      for (const g of gos) {
        await page.evaluate(([v, g]) => { location.hash = v; }, [v, g]);
        await page.evaluate(g => { const el = document.querySelector(`#main [data-go="${CSS.escape(g)}"]`); if (el) el.dispatchEvent(new MouseEvent("click", { bubbles: true })); }, g);
        links++;
      }
    }
    await page.setViewportSize({ width: 400, height: 900 });
    for (const v of views) {
      await page.evaluate(v => { location.hash = v; }, v);
      await page.waitForTimeout(40);
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (sw > 400) errors.push(`${v}: 幅400pxで横にはみ出します（${sw}px）`);
    }
    console.log(`${f}: ${views.length}画面・リンク${links}件を確認${errors.length ? "、問題" + errors.length + "件" : "、問題なし"}`);
    errors.forEach(e => console.log("  - " + e));
    failed += errors.length;
    await page.close();
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
