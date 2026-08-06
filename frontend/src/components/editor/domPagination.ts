// HTML_to_PDF injects `@page { size: A4; margin: 0 !important }` and sets
// preferCSSPageSize=true. Chrome therefore fragments the DOM on the full A4
// canvas; the CDP margin values do not reduce the CSS fragmentation viewport.
const PRINTABLE_PAGE_HEIGHT_PX = 11.69 * 96;
const PAGE_GAP_PX = 28;
const PRINTABLE_PAGE_WIDTH_PX = 8.27 * 96;
const ATOMIC_SELECTOR = [
  "header",
  ".entry",
  ".resume-card",
  ".skills-container",
  "#technical-stack",
  "#languages-other",
  "#skills-languages",
  ".two-column",
  ".compact-list",
  ".stack-list",
  ".inline-list",
  "li",
].join(",");

/** Apply the same print-only template rules and width used by Chrome PDF. */
export function installPrintLayoutEmulation(doc: Document): void {
  doc.getElementById("buping-print-layout-emulation")?.remove();
  const printRules: string[] = [];
  for (const sheet of Array.from(doc.styleSheets)) {
    try {
      for (const rule of Array.from(sheet.cssRules)) {
        if (rule.type === CSSRule.MEDIA_RULE) {
          const mediaRule = rule as CSSMediaRule;
          if (!mediaRule.conditionText.toLowerCase().includes("print")) continue;
          printRules.push(...Array.from(mediaRule.cssRules).map((child) => child.cssText));
        }
      }
    } catch {
      // Cross-origin stylesheets cannot be inspected; resume template CSS is embedded.
    }
  }

  const style = doc.createElement("style");
  style.id = "buping-print-layout-emulation";
  style.textContent = `
    ${printRules.join("\n")}
    *, *::before, *::after { box-sizing: border-box !important; }
    html {
      width: ${PRINTABLE_PAGE_WIDTH_PX}px !important;
      min-width: ${PRINTABLE_PAGE_WIDTH_PX}px !important;
      max-width: ${PRINTABLE_PAGE_WIDTH_PX}px !important;
      margin: 0 auto !important;
      padding: 0 !important;
    }
    body {
      width: 100% !important;
      max-width: none !important;
      margin: 0 !important;
      padding: 8px !important;
      text-align: left !important;
      direction: ltr !important;
      float: none !important;
    }
    body > * {
      margin-left: auto !important;
      margin-right: auto !important;
      float: none !important;
      max-width: 720px !important;
      width: auto !important;
    }
  `;
  doc.head.appendChild(style);
}

/**
 * Paginate the editable DOM using the same atomic-block policy as print CSS.
 * A spacer represents the unused tail of the current PDF page plus a visible
 * gap, so following content begins at the top of the next on-screen page.
 */
export function paginateResumeDom(doc: Document): void {
  doc.querySelectorAll("[data-buping-page-break]").forEach((node) => node.remove());
  const bodyTop = doc.body.getBoundingClientRect().top;
  let pageStart = 0;
  let pageNumber = 1;
  const blocks = Array.from(doc.body.querySelectorAll<HTMLElement>(ATOMIC_SELECTOR))
    // Only paginate the outermost matching block; nested li/list matches must
    // not create duplicate breaks for the same content.
    .filter((block) => !block.parentElement?.closest(ATOMIC_SELECTOR));

  for (const block of blocks) {
    let rect = block.getBoundingClientRect();
    let breakTarget = block;
    const previous = block.previousElementSibling as HTMLElement | null;
    if (previous?.matches("h1, h2, h3, .entry-header, .entry-details")) {
      breakTarget = previous;
    }
    let top = breakTarget.getBoundingClientRect().top - bodyTop;
    let bottom = rect.bottom - bodyTop;
    const blockHeight = rect.height;
    const pageEnd = pageStart + PRINTABLE_PAGE_HEIGHT_PX;
    if (blockHeight >= PRINTABLE_PAGE_HEIGHT_PX || bottom <= pageEnd + 0.5) continue;

    const spacer = doc.createElement("div");
    const remainingOnPage = Math.max(0, pageEnd - top);
    spacer.setAttribute("data-buping-page-break", "true");
    spacer.setAttribute("contenteditable", "false");
    spacer.style.cssText = [
      `height:${remainingOnPage + PAGE_GAP_PX}px`,
      "position:relative",
      "pointer-events:none",
      "box-sizing:border-box",
      "width:100%",
      "grid-column:1 / -1",
      "flex:0 0 100%",
      "clear:both",
    ].join(";");
    const line = doc.createElement("div");
    line.style.cssText = [
      "position:absolute",
      "left:0",
      "width:100%",
      `top:${remainingOnPage}px`,
      `height:${PAGE_GAP_PX}px`,
      "border-top:2px dashed rgba(225,29,72,.72)",
      "background:linear-gradient(to bottom,rgba(244,244,245,.9),rgba(255,255,255,0))",
      "box-sizing:border-box",
    ].join(";");
    const label = doc.createElement("span");
    label.textContent = `PDF 第 ${pageNumber} 页结束 / 第 ${pageNumber + 1} 页开始`;
    label.style.cssText = "position:absolute;right:8px;top:4px;color:#be123c;font:11px/16px system-ui,sans-serif";
    line.appendChild(label);
    spacer.appendChild(line);
    breakTarget.parentNode?.insertBefore(spacer, breakTarget);

    rect = block.getBoundingClientRect();
    top = breakTarget.getBoundingClientRect().top - bodyTop;
    bottom = rect.bottom - bodyTop;
    pageStart = top;
    pageNumber += 1;
  }
}
