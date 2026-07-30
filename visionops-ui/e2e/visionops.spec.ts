import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_URL = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8001";
const API_KEY = process.env.VISIONOPS_API_KEY ?? "visionops-dev-key";
const apiHeaders = { "X-API-Key": API_KEY };

type Camera = { id: string; name: string };
type Alert = { id: string };

function unique(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function createCamera(request: APIRequestContext, name: string): Promise<Camera> {
  const response = await request.post(`${API_URL}/api/v1/cameras`, {
    headers: apiHeaders,
    data: {
      name,
      source_url: `rtsp://127.0.0.1:8554/${name}`,
      location: "E2E",
      is_active: true,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function deleteCamera(request: APIRequestContext, id: string): Promise<void> {
  try {
    const response = await request.delete(`${API_URL}/api/v1/cameras/${id}`, {
      headers: apiHeaders,
    });
    expect([204, 404]).toContain(response.status());
  } catch {
    // Stack may still be restarting during local development.
  }
}

async function cleanupCameraByName(
  request: APIRequestContext,
  name: string,
): Promise<void> {
  try {
    const cameras = await request.get(`${API_URL}/api/v1/cameras`, {
      headers: apiHeaders,
    });
    if (!cameras.ok()) return;
    const leftover = ((await cameras.json()) as Camera[]).find(
      (camera) => camera.name === name,
    );
    if (leftover) await deleteCamera(request, leftover.id);
  } catch {
    // Best-effort cleanup only.
  }
}

async function selectCameraOnLoad(page: Page, id: string): Promise<void> {
  await page.addInitScript((cameraId) => {
    window.localStorage.setItem("visionops.selectedCameraId", cameraId);
  }, id);
}

test("camera CRUD is usable from the dashboard", async ({ page, request }) => {
  const name = unique("e2e-camera");
  try {
    await page.goto("/cameras");

    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Source URL").fill(`rtsp://127.0.0.1:8554/${name}`);
    await page.getByLabel("Location").fill("Dock E2E");
    await page.getByRole("button", { name: "Create", exact: true }).click();

    const card = page.locator("article").filter({ hasText: name });
    await expect(card).toContainText("Dock E2E");

    await card.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Location").fill("Gate E2E");
    await page.getByRole("button", { name: "Update" }).click();
    await expect(page.locator("article").filter({ hasText: name })).toContainText("Gate E2E");

    page.once("dialog", (dialog) => dialog.accept());
    await page
      .locator("article")
      .filter({ hasText: name })
      .getByRole("button", { name: "Delete" })
      .click();
    await expect(page.locator("article").filter({ hasText: name })).toHaveCount(0);
  } finally {
    await cleanupCameraByName(request, name);
  }
});

test("ROI polygon can be created and removed", async ({ page, request }) => {
  const cameraName = unique("e2e-roi-camera");
  const zoneName = unique("e2e-zone");
  const camera = await createCamera(request, cameraName);

  try {
    await selectCameraOnLoad(page, camera.id);
    await page.goto("/roi");
    await expect(page.getByLabel("Camera")).toHaveValue(camera.id);
    await expect(page.getByText(`Camera ${cameraName}`, { exact: false })).toBeVisible();

    const canvas = page.locator("canvas");
    await expect(canvas).toBeVisible();
    await canvas.click({ position: { x: 80, y: 70 } });
    await canvas.click({ position: { x: 280, y: 70 } });
    await canvas.click({ position: { x: 280, y: 220 } });
    await canvas.click({ position: { x: 80, y: 220 } });
    await expect(page.getByText("Draft points: 4")).toBeVisible();

    await page.getByLabel("Zone name").fill(zoneName);
    await page.getByRole("button", { name: "Save ROI" }).click();
    await expect(page.getByText(zoneName, { exact: true })).toBeVisible();

    const zoneRow = page.locator("div").filter({ hasText: zoneName }).last();
    await zoneRow.getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText(zoneName, { exact: true })).toHaveCount(0);
  } finally {
    await deleteCamera(request, camera.id);
  }
});

test("incident can be assigned, commented and resolved", async ({ page, request }) => {
  const cameraName = unique("e2e-alert-camera");
  const message = unique("E2E incident");
  const camera = await createCamera(request, cameraName);
  let alert: Alert | undefined;

  try {
    const created = await request.post(`${API_URL}/api/v1/alerts`, {
      headers: apiHeaders,
      data: {
        camera_id: camera.id,
        alert_type: "roi_intrusion",
        zone_name: "e2e-zone",
        class_name: "person",
        message,
        enqueue_media: false,
      },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
    alert = await created.json();

    await selectCameraOnLoad(page, camera.id);
    await page.goto("/alerts");
    const card = page.locator("article").filter({ hasText: message });
    await expect(card).toBeVisible();
    await expect(card).toContainText("open");

    await card.getByLabel("Assignee").fill("e2e-operator");
    await card.getByLabel("Note").fill("E2E assignment");
    await card.getByRole("button", { name: "Assign" }).click();
    await expect(card).toContainText("acknowledged");
    await expect(card).toContainText("assigned e2e-operator");

    await card.getByPlaceholder("Add a comment").fill("E2E checked");
    await card.getByRole("button", { name: "Comment" }).click();
    await expect(card.getByPlaceholder("Add a comment")).toHaveValue("");
    await card.getByLabel("Note").fill("E2E resolved");
    await card.getByRole("button", { name: "Resolve" }).click();
    await expect(card).toContainText("resolved");
    await expect(card).toContainText("Resolution: E2E resolved");

    await card.getByRole("button", { name: /history/i }).click();
    await expect(card.getByText("E2E checked", { exact: true })).toBeVisible();
  } finally {
    if (alert) {
      await request.delete(`${API_URL}/api/v1/alerts/${alert.id}`, { headers: apiHeaders });
    }
    await deleteCamera(request, camera.id);
  }
});
