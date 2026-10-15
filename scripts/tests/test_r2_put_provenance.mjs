import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "../..");
const helperPath = path.join(root, "cloudflare/runner3-core/src/r2-put-provenance.js");
const source = readFileSync(helperPath, "utf8");
const mod = await import("data:text/javascript," + encodeURIComponent(source));

const labels = [
  "artifact-api",
  "rss-original",
  "rss-translation",
  "rss-import-media",
  "rss-import-original-rewrite",
  "rss-cache-image",
  "rss-cache-original-rewrite",
  "seotrends-emergency-sitemap",
  "seotrends-emergency-item",
  "seotrends-emergency-manifest",
  "seotrends-status",
];

const original = console.info;
const messages = [];
try {
  console.info = (...args) => messages.push(args.join(" "));
  for (const label of labels) {
    assert.equal(mod.traceR2PutCompleted({}, label), false, "disabled");
  }
  assert.equal(messages.length, 0, "no logs by default");
  assert.equal(mod.traceR2PutCompleted({ R2_PUT_PROVENANCE: "enabled" }, "arbitrary-user-value"), false);
  assert.equal(messages.length, 0, "reject unrecognized caller");
  for (const label of labels) {
    assert.equal(mod.traceR2PutCompleted({ R2_PUT_PROVENANCE: "enabled" }, label), true);
  }
  assert.equal(messages.length, labels.length, "one log per completed write");
  for (let i=0;i<messages.length;i++) {
    const row=JSON.parse(messages[i]);
    assert.deepEqual(Object.keys(row).sort(), ["bucket", "event", "version", "writer"]);
    assert.equal(row.writer, labels[i]);
    assert.equal(row.bucket, "runner3-artifacts");
    assert.equal(row.event, "r2.put.completed");
  }
  console.info = () => { throw Error("logging blocked"); };
  assert.equal(mod.traceR2PutCompleted({ R2_PUT_PROVENANCE: "enabled" }, "artifact-api"), false);
} finally {
  console.info = original;
}
const expected = new Map([
  ["index.js",1],
  ["rss-library.js",2],
  ["rss-library-save.js",2],
  ["rss-image-enrich.js",2],
]);
for (const [file,n] of expected) {
  const s=readFileSync(path.join(root,"cloudflare/runner3-core/src",file),"utf8");
  assert.equal((s.match(/traceR2PutCompleted\(env, "/g)||[]).length,n,file);
  assert.ok(s.startsWith('import { traceR2PutCompleted } from "./r2-put-provenance.js";'),file);
}
console.log("PASS r2-put-provenance: opt-in, no sensitive payload, error isolation, writer-site coverage");
