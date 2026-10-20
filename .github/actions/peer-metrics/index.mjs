// JavaScript action so saveCache sees ACTIONS_RESULTS_URL. A `run` step
// does not receive the cache service URL, and saveCache then returns -1.
import { spawn, execFile } from "node:child_process";
import { appendFileSync, createWriteStream, mkdirSync } from "node:fs";
import { promisify } from "node:util";
import { saveCache } from "@actions/cache";

const execFileAsync = promisify(execFile);
const workspace = process.env.GITHUB_WORKSPACE;
const base = process.env.INPUT_BASE || "main";
const dryRun = (process.env.INPUT_DRY_RUN || "false") === "true";
const outFile = "/tmp/sic-peers.txt";
const cachePaths = [
  "backend/.cache/companyfacts",
  "backend/.cache/quotes",
  "backend/.cache/peer_metrics_ckpt",
  "backend/.cache/fred",
].map((p) => `${workspace}/${p}`);

for (const dir of cachePaths) mkdirSync(dir, { recursive: true });

function fail(message) {
  process.stdout.write(`::error::${message}\n`);
  process.exit(1);
}

async function saveOne(key, deleteKey) {
  const id = await saveCache(cachePaths, key);
  if (id === -1) {
    throw new Error(`cache save returned -1 for ${key}`);
  }
  process.stdout.write(`cache-saved key=${key} id=${id}\n`);
  if (deleteKey && deleteKey !== "-") {
    try {
      const args = ["cache", "delete", deleteKey, "--ref", process.env.GITHUB_REF];
      await execFileAsync("gh", args, { env: process.env });
      process.stdout.write(`cache-deleted key=${deleteKey}\n`);
    } catch (err) {
      process.stdout.write(`cache-delete-skip key=${deleteKey} ${err.message}\n`);
    }
  }
}

const summary = createWriteStream(outFile);
const child = spawn(
  "uv",
  [
    "run",
    "python",
    "-u",
    "-m",
    "app.peer_metrics",
    "--old-sic",
    "/tmp/sic_peers.old.json",
    ...(dryRun ? ["--dry-run"] : []),
  ],
  {
    cwd: `${workspace}/backend`,
    env: { ...process.env, SIC_PEERS_CACHE_IPC: "1", PYTHONUNBUFFERED: "1" },
    stdio: ["pipe", "pipe", "inherit"],
  },
);

let pending = Promise.resolve();
let buf = "";
let changed = "false";

function takeLine(line) {
  if (line.startsWith("@@cache ")) {
    const parts = line.trim().split(/\s+/);
    const key = parts[1];
    const deleteKey = parts[2] || "-";
    if (!key) fail("cache ipc line missing key");
    pending = pending.then(async () => {
      try {
        await saveOne(key, deleteKey);
      } catch (err) {
        const msg = err && err.message ? err.message : String(err);
        child.stdin.write(`@@cache-err ${msg}\n`);
        throw err;
      }
      child.stdin.write("@@cache-ok\n");
    });
    return;
  }
  summary.write(line + "\n");
  process.stdout.write(line + "\n");
  if (line.startsWith("changed=")) changed = line.slice("changed=".length);
}

child.stdout.on("data", (chunk) => {
  buf += chunk.toString();
  let nl;
  while ((nl = buf.indexOf("\n")) !== -1) {
    takeLine(buf.slice(0, nl));
    buf = buf.slice(nl + 1);
  }
});

child.on("close", async (code) => {
  if (buf) takeLine(buf);
  summary.end();
  try {
    await pending;
  } catch (err) {
    fail(err && err.message ? err.message : String(err));
  }
  if (code !== 0) fail(`peer_metrics exited ${code}`);
  const file = process.env.GITHUB_OUTPUT;
  if (file) appendFileSync(file, `changed=${changed}\n`);
});
