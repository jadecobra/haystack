// Save a GitHub Actions cache from the peer_metrics chunk loop.
// Usage: node save-actions-cache.mjs <key> <delete-key|-> <path>...
// A duplicate key or a failed delete does not fail the metrics build.
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const require = createRequire(fileURLToPath(import.meta.url));
const { saveCache } = require("@actions/cache");

const [key, deleteKey, ...paths] = process.argv.slice(2);
if (!key || !deleteKey || paths.length === 0) {
  console.error("usage: save-actions-cache.mjs <key> <delete-key|-> <path>...");
  process.exit(2);
}

try {
  const id = await saveCache(paths, key);
  console.log(`cache-saved key=${key} id=${id}`);
} catch (err) {
  const msg = err && err.message ? err.message : String(err);
  console.log(`cache-save-skip key=${key} ${msg}`);
  process.exit(0);
}

if (deleteKey !== "-") {
  try {
    const args = ["cache", "delete", deleteKey];
    if (process.env.GITHUB_REF) args.push("--ref", process.env.GITHUB_REF);
    execFileSync("gh", args, { stdio: "inherit" });
    console.log(`cache-deleted key=${deleteKey}`);
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    console.log(`cache-delete-skip key=${deleteKey} ${msg}`);
  }
}
