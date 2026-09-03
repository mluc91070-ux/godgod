/**
 * Does the site fit on a phone, and does it say so or does it just look like it?
 *
 * Written because a screenshot lied. Chrome's CLI on Windows will not open a
 * window narrower than about 500px: asking for 390 lays the page out at 500 and
 * crops the capture, so every "mobile" screenshot came back with the right-hand
 * side sheared off and looked exactly like a real overflow bug. It was an
 * artefact of the tool. This runs a real viewport instead, and measures rather
 * than photographs.
 *
 * Two things are checked at each width, and neither is a matter of opinion:
 *
 * - **horizontal overflow.** `documentElement.scrollWidth` greater than the
 *   viewport means the page scrolls sideways. The body carries
 *   `overflow-x-hidden`, which means it does not scroll — it *clips*, silently,
 *   and content past the edge is unreachable rather than merely awkward. That
 *   makes this the failure worth catching automatically.
 * - **which element caused it.** A boolean is not actionable, so every element
 *   whose right edge passes the viewport is reported with its width and its
 *   classes.
 *
 *   node scripts/ux-audit.mjs [baseUrl]
 */

import { chromium, devices } from "playwright";

const BASE = process.argv[2] ?? "http://127.0.0.1:3130";

const PAGES = [
  "/",
  "/terminal",
  "/observe",
  "/data",
  "/pairings",
  "/watchlist",
  "/thesis",
  "/hypotheses",
  "/experiments",
  "/findings",
  "/patterns",
  "/memory",
  "/agents",
  "/roadmap",
  "/token",
  "/lore",
  "/about",
  "/docs",
  "/research",
];

const VIEWPORTS = [
  { name: "iphone-se", width: 320, height: 900 },
  { name: "iphone-12", width: 390, height: 900 },
  { name: "tablet", width: 768, height: 1000 },
  { name: "desktop", width: 1440, height: 1000 },
];

const audit = () => {
  const vw = document.documentElement.clientWidth;
  const offenders = [];
  for (const el of document.querySelectorAll("body *")) {
    const style = getComputedStyle(el);
    if (style.position === "fixed" || style.display === "none") continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1) {
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute("class") ?? "").slice(0, 110),
        text: (el.textContent ?? "").trim().slice(0, 60),
        width: Math.round(r.width),
        right: Math.round(r.right),
      });
    }
  }
  // Innermost only: a parent overflows because its child does, and reporting
  // the whole ancestor chain buries the one element worth changing.
  const leaves = offenders.filter(
    (o, i) => !offenders.some((p, j) => j !== i && p.right >= o.right && p.width > o.width),
  );
  return {
    viewport: vw,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: leaves.slice(0, 8),
  };
};

const browser = await chromium.launch();
let failures = 0;

for (const vp of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: 1,
    ...(vp.width < 640 ? devices["iPhone 12"].userAgent : {}),
  });
  const page = await context.newPage();

  for (const path of PAGES) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 45_000 });
    const report = await page.evaluate(audit);
    const overflow = report.scrollWidth > report.viewport + 1;
    if (overflow || report.offenders.length) {
      failures += 1;
      console.log(
        `FAIL ${vp.name.padEnd(10)} ${path.padEnd(14)} viewport=${report.viewport} scrollWidth=${report.scrollWidth}`,
      );
      for (const o of report.offenders) {
        console.log(`       ${o.width}w right=${o.right} <${o.tag}> ${o.cls}`);
        if (o.text) console.log(`         "${o.text}"`);
      }
    } else {
      console.log(`ok   ${vp.name.padEnd(10)} ${path.padEnd(14)} ${report.viewport}px`);
    }
  }
  await context.close();
}

await browser.close();
console.log(failures ? `\n${failures} page/viewport combinations overflow` : "\nno overflow at any width");
process.exit(failures ? 1 : 0);
