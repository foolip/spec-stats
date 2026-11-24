// Serves out/ as GitHub Pages would: under SITE_BASE (/spec-stats), a
// directory's index.html, and 404.html with status 404 for anything else.
// Usage: node scripts/serve.mjs [port]

import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const base = (process.env.SITE_BASE ?? "/spec-stats").replace(/\/$/, "");
const root = path.resolve("out");
const port = Number(process.argv[2] ?? 8080);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8", ".woff2": "font/woff2" };

async function file(p) {
  try {
    const s = await stat(p);
    if (s.isDirectory()) return file(path.join(p, "index.html"));
    return p;
  } catch {
    return null;
  }
}

createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://localhost");
  let found = null;
  if (pathname === base || pathname.startsWith(base + "/")) {
    const rel = decodeURIComponent(pathname.slice(base.length));
    const p = path.join(root, rel);
    if (p.startsWith(root)) found = await file(p);
    if (found && !rel.endsWith("/") && found.endsWith("index.html") && !rel.endsWith("index.html")) {
      res.writeHead(301, { location: pathname + "/" }).end();
      return;
    }
  }
  const status = found ? 200 : 404;
  const p = found ?? path.join(root, "404.html");
  res.writeHead(status, { "content-type": types[path.extname(p)] ?? "application/octet-stream", "cache-control": "max-age=600" });
  res.end(await readFile(p));
}).listen(port, () => console.log(`http://localhost:${port}${base}/`));
