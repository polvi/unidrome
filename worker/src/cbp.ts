// Scrape the CBP "General Aviation Airport Fact Sheets" index and resolve each
// airport ident to its current PDF URL. Mirrors scripts/cbp-factsheets.py
// scrape_factsheets() exactly (same pagination, regexes, ident rules).

const CBP_BASE = "https://www.cbp.gov";
const INDEX =
  "https://www.cbp.gov/newsroom/publications/general-aviation-airport-fact-sheets?page=";
const INDEX_PAGES = 28; // pages 0..27

const PDF_HREF = /href="([^"]+\.pdf)"/gi;
const GA_SHEET = /ga[ _]?airport[ _]?fact[ _]?sheet/i;
const IDENT_OK = /^[A-Z0-9]{3,5}$/;

async function getText(url: string, ua: string): Promise<string> {
  const res = await fetch(url, {
    headers: { "User-Agent": ua },
    signal: AbortSignal.timeout(20000), // don't let a slow page hang the run
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.text();
}

/** Return { ident: absolute_pdf_url } for every GA airport fact sheet. */
export async function scrapeFactsheets(
  ua: string,
): Promise<Record<string, string>> {
  const sheets: Record<string, string> = {};
  for (let n = 0; n < INDEX_PAGES; n++) {
    let html: string;
    try {
      html = await getText(INDEX + n, ua);
    } catch (e) {
      console.log(`page ${n}: ${e}`);
      continue;
    }
    for (const m of html.matchAll(PDF_HREF)) {
      const href = m[1];
      const name = (href.split("/").pop() || "").replace(/%20/g, " ");
      if (!GA_SHEET.test(name)) continue;
      const ident = name.split(/[ _]/)[0].toUpperCase();
      if (!IDENT_OK.test(ident)) continue;
      const url = href.startsWith("http") ? href : CBP_BASE + href;
      sheets[ident] = url; // dedupe by ident, newest page wins
    }
  }
  return sheets;
}

export interface FetchedPdf {
  bytes: Uint8Array;
  etag: string | null;
}

/** Download a fact sheet PDF, validating the %PDF magic. */
export async function fetchPdf(
  url: string,
  ua: string,
): Promise<FetchedPdf | null> {
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { "User-Agent": ua },
      signal: AbortSignal.timeout(30000),
    });
  } catch (e) {
    console.log(`  fetch ${url}: ${e}`); // timeout / network — skip, retry next run
    return null;
  }
  if (!res.ok) {
    console.log(`  fetch ${url}: HTTP ${res.status}`);
    return null;
  }
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (
    bytes.length < 4 ||
    bytes[0] !== 0x25 || // %
    bytes[1] !== 0x50 || // P
    bytes[2] !== 0x44 || // D
    bytes[3] !== 0x46 //   F
  ) {
    console.log(`  ${url}: not a PDF, skipping`);
    return null;
  }
  return { bytes, etag: res.headers.get("etag") };
}
