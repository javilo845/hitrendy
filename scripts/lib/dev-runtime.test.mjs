import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { apiUrl, localhostUrl } from "./dev-runtime.mjs";

describe("dev runtime URLs", () => {
  it("derives every local URL from the selected port", () => {
    assert.equal(localhostUrl(3017), "http://localhost:3017");
    assert.equal(localhostUrl(8017, "127.0.0.1"), "http://127.0.0.1:8017");
    assert.equal(apiUrl(8017), "http://127.0.0.1:8017/api/v1");
  });
});
