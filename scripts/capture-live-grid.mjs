/**
 * Capture docs/screenshots/live-grid.png
 *
 * Default: render the static docs mock (no stack required).
 * With CAPTURE_LIVE=1 and UI+API up: seed 3 cams and shoot /monitor Grid.
 *
 * Usage (from repo root):
 *   node scripts/capture-live-grid.mjs
 *   CAPTURE_LIVE=1 node scripts/capture-live-grid.mjs
 */
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { extname, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const uiRoot = join(root, "visionops-ui");
const requireFromUi = createRequire(join(uiRoot, "package.json"));
const { chromium } = requireFromUi("playwright");

const shots = join(root, "docs", "screenshots");
const outPath = join(shots, "live-grid.png");
const live = process.env.CAPTURE_LIVE === "1";
const apiUrl = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8001";
const uiUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";
const apiKey = process.env.VISIONOPS_API_KEY ?? "visionops-dev-key";
const adminUser = process.env.VISIONOPS_ADMIN_USERNAME ?? "admin";
const adminPass = process.env.VISIONOPS_ADMIN_PASSWORD ?? "visionops-admin";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".css": "text/css",
};

function serveDocs() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const urlPath = decodeURIComponent((req.url ?? "/").split("?")[0]);
      const rel = urlPath === "/" ? "/render-live-grid.html" : urlPath;
      const file = join(shots, rel.replace(/^\//, ""));
      if (!file.startsWith(shots) || !existsSync(file)) {
        res.writeHead(404);
        res.end("missing");
        return;
      }
      res.writeHead(200, { "Content-Type": MIME[extname(file)] ?? "application/octet-stream" });
      res.end(readFileSync(file));
    });
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ server, base: `http://127.0.0.1:${port}` });
    });
  });
}

async function seedCameras() {
  const headers = {
    "X-API-Key": apiKey,
    "Content-Type": "application/json",
  };
  const listRes = await fetch(`${apiUrl}/api/v1/cameras`, { headers });
  if (!listRes.ok) throw new Error(`list cameras: ${listRes.status}`);
  const existing = await listRes.json();
  const cams = [
    { name: "entrance", source_url: "rtsp://mediamtx:8554/cam1", location: "Main gate" },
    { name: "parking-lot", source_url: "rtsp://mediamtx:8554/cam2", location: "Lot A" },
    { name: "loading-dock", source_url: "rtsp://mediamtx:8554/cam3", location: "Dock 2" },
  ];
  for (const cam of cams) {
    const found = existing.find((c) => c.name === cam.name);
    if (found) {
      await fetch(`${apiUrl}/api/v1/cameras/${found.id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ ...cam, is_active: true }),
      });
    } else {
      await fetch(`${apiUrl}/api/v1/cameras`, {
        method: "POST",
        headers,
        body: JSON.stringify({ ...cam, is_active: true }),
      });
    }
  }
}

async function captureLive(browser) {
  await seedCameras();
  const login = await fetch(`${apiUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: adminUser, password: adminPass }),
  });
  if (!login.ok) throw new Error(`login failed: ${login.status}`);
  const body = await login.json();

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(
    ({ token, user }) => {
      localStorage.setItem("visionops.accessToken", token);
      localStorage.setItem("visionops.authUser", JSON.stringify(user));
      localStorage.setItem("visionops.monitorLayout", "grid");
    },
    { token: body.access_token, user: body.user },
  );
  await page.goto(`${uiUrl}/monitor`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Grid" }).click();
  const source = page.locator("label").filter({ hasText: "Video source" }).locator("select");
  if (await source.count()) {
    await source.selectOption("demo");
  }
  await page.waitForTimeout(2500);
  await page.screenshot({ path: outPath, fullPage: false });
  await page.close();
}

async function captureMock(browser) {
  const { server, base } = await serveDocs();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.goto(`${base}/render-live-grid.html`, { waitUntil: "networkidle" });
    await page.waitForSelector("#capture-root");
    await page.waitForFunction(() =>
      [...document.images].every((img) => img.complete && img.naturalWidth > 0),
    );
    await page.locator("#capture-root").screenshot({ path: outPath });
    await page.close();
  } finally {
    server.close();
  }
}

const browser = await chromium.launch();
try {
  if (live) {
    console.log("Capturing live UI grid…");
    await captureLive(browser);
  } else {
    console.log("Capturing docs mock grid…");
    await captureMock(browser);
  }
  console.log(`Wrote ${outPath}`);
} finally {
  await browser.close();
}
