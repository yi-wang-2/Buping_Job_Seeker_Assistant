/**
 * Extract CSS styles and clean body content from a full HTML document.
 *
 * Input HTML is the complete resume page (e.g. from /preview-saved):
 *   <!DOCTYPE html><html><head><style>...CSS...</style></head><body>...CONTENT...</body></html>
 *
 * Returns:
 *   - css: combined style block content
 *   - body: inner HTML of the body element (no <body> wrapper)
 *   - hasStyle: whether any CSS was found
 */
export interface ExtractedStyle {
  css: string;
  body: string;
  hasStyle: boolean;
}

export function extractStyleFromHtml(html: string): ExtractedStyle {
  if (typeof window === "undefined" || !html) {
    return { css: "", body: html || "", hasStyle: false };
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  // Collect ALL <style> tag content (from head and body)
  const styleEls = doc.querySelectorAll("style");
  let css = "";
  styleEls.forEach((el) => {
    css += el.textContent + "\n";
  });

  // Extract <body> innerHTML (strip <body> wrapper if present)
  let body = doc.body?.innerHTML || html;
  const bodyMatch = body.match(/^<body[^>]*>([\s\S]*)<\/body>$/i);
  if (bodyMatch) {
    body = bodyMatch[1];
  }

  return {
    css: css.trim(),
    body,
    hasStyle: css.trim().length > 0,
  };
}