import assert from "node:assert/strict";
import test from "node:test";

import {
  allowedSessionResource,
  whepEndpoint,
} from "./targets.mjs";

const BASE = "http://127.0.0.1:8889";

test("builds WHEP endpoint only from a safe stream identifier", () => {
  assert.equal(whepEndpoint(BASE, "cam1")?.toString(), `${BASE}/cam1/whep`);
  assert.equal(whepEndpoint(BASE, "../admin"), null);
  assert.equal(whepEndpoint(BASE, "cam1?target=http://internal"), null);
});

test("accepts same-origin WHEP session resources", () => {
  const target = allowedSessionResource(BASE, "/cam1/whep/session-id");
  assert.equal(target?.toString(), `${BASE}/cam1/whep/session-id`);
});

test("rejects external and non-WHEP DELETE targets", () => {
  assert.equal(
    allowedSessionResource(BASE, "http://169.254.169.254/latest/meta-data"),
    null,
  );
  assert.equal(allowedSessionResource(BASE, `${BASE}/v3/config/paths/list`), null);
  assert.equal(allowedSessionResource(BASE, "file:///etc/passwd"), null);
});
