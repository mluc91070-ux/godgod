/**
 * Is any page on the live site blank?
 *
 * "Blank" is not a look, it is a measurement: how much text a reader actually
 * gets below the chrome. The nav, the status strip and the footer are on every
 * page and are identical, so counting the whole document says every page is
 * full even when the middle of it is empty. This subtracts them and reports
 * what is left.
 *
 * It also reports whether the page fell back to an unreachable-API state, since
 * that is the difference between a page with nothing to say and a page that
 * could not ask.
 *
 *   node scripts/content-audit.mjs https://godgod.tech
 */

import { chromium } from "playwright";

const BASE = process.argv[2] ?? "https://godgod.tech";
const FLOOR = 400; // characters of body text below which a page is not saying anything

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

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();

let thin = 0;
let unreachable = 0;

for (const path of PAGES) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 60_000 });
  const report = await page.evaluate(() => {
    const chrome = ["header", "footer"];
    const clone = document.body.cloneNode(true);
    for (const sel of chrome) clone.querySelectorAll(sel).forEach((el) => el.remove());
    // The status strip is a bare div under the header, not a landmark.
    const strip = clone.querySelector("div");
    if (strip && (strip.textContent ?? "").includes("AUTONOMY")) strip.remove();
    const text = (clone.textContent ?? "").replace(/\s+/g, " ").trim();
    return {
      chars: text.length,
      apiDown: /api unreachable|did not answer|unreachable:/i.test(text),
      head: text.slice(0, 80),
    };
  });

  const flag = report.chars < FLOOR ? "THIN" : "ok  ";
  if (report.chars < FLOOR) thin += 1;
  if (report.apiDown) unreachable += 1;
  console.log(
    `${flag} ${path.padEnd(14)} ${String(report.chars).padStart(6)} chars` +
      `${report.apiDown ? "  [api unreachable]" : ""}  ${report.head}`,
  );
}

await browser.close();
console.log(
  `\n${PAGES.length} pages · ${thin} under ${FLOOR} chars · ${unreachable} showing an unreachable API`,
);
process.exit(thin ? 1 : 0);
