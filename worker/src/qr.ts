// Inline QR code as SVG, generated server-side (no external image service, no
// DOM). qrcode-generator's encoder is pure JS and works in Workers.

import qrcode from "qrcode-generator";

/** Return an <svg> string encoding `text` (black modules on white). */
export function qrSvg(text: string, cell = 4, margin = 4): string {
  const qr = qrcode(0, "M"); // 0 = auto-size, M = ~15% error correction
  qr.addData(text);
  qr.make();
  const count = qr.getModuleCount();
  const dim = (count + margin * 2) * cell;

  let rects = "";
  for (let r = 0; r < count; r++) {
    for (let c = 0; c < count; c++) {
      if (!qr.isDark(r, c)) continue;
      const x = (c + margin) * cell;
      const y = (r + margin) * cell;
      rects += `<rect x="${x}" y="${y}" width="${cell}" height="${cell}"/>`;
    }
  }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${dim}" height="${dim}" ` +
    `viewBox="0 0 ${dim} ${dim}" shape-rendering="crispEdges" role="img">` +
    `<rect width="${dim}" height="${dim}" fill="#fff"/>` +
    `<g fill="#000">${rects}</g></svg>`
  );
}
