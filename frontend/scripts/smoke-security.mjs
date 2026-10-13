import assert from "node:assert/strict";

const origin = process.env.SMOKE_ORIGIN || "http://127.0.0.1:3011";
for (let attempt = 0; attempt < 40; attempt++) {
  try {
    await fetch(origin);
    break;
  } catch (error) {
    if (attempt === 39) throw error;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}
const responses = await Promise.all([fetch(origin), fetch(origin)]);
const nonces = [];
for (const response of responses) {
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-frame-options"), "DENY");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  assert.equal(response.headers.get("cache-control"), "no-store");
  const csp = response.headers.get("content-security-policy");
  assert.ok(csp?.includes("frame-ancestors 'none'"));
  assert.ok(!csp.includes("'unsafe-eval'"));
  assert.ok(!csp.match(/script-src[^;]*'unsafe-inline'/));
  const nonce = csp.match(/'nonce-([^']+)'/)?.[1];
  assert.ok(nonce);
  const body = await response.text();
  assert.ok(body.includes(`nonce="${nonce}"`));
  nonces.push(nonce);
}
assert.notEqual(nonces[0], nonces[1]);
console.log(
  "Frontend security smoke passed: headers, no-store, per-response CSP nonces and rendered script nonce.",
);
