import assert from "node:assert/strict";
import path from "node:path";
import { describe, it } from "node:test";
import { ESLint } from "eslint";

const FRONTEND_DIR = import.meta.dirname;

function createLinter() {
  return new ESLint({
    cwd: FRONTEND_DIR,
    overrideConfigFile: path.join(FRONTEND_DIR, "eslint.config.mjs"),
  });
}

async function lintSnippet(relPath, code) {
  const eslint = createLinter();
  const [result] = await eslint.lintText(code, {
    filePath: path.join(FRONTEND_DIR, relPath),
  });
  return result.messages;
}

describe("frontend eslint boundaries (#168)", () => {
  it("forbids react imports inside lib/", async () => {
    const messages = await lintSnippet(
      "lib/fake.ts",
      'import { useState } from "react";\nexport const x = useState;\n',
    );
    assert.ok(
      messages.some((m) => m.ruleId === "no-restricted-imports"),
      `expected no-restricted-imports, got: ${JSON.stringify(messages)}`,
    );
  });

  it("forbids next/* imports inside lib/", async () => {
    const messages = await lintSnippet(
      "lib/fake.ts",
      'import Link from "next/link";\nexport const L = Link;\n',
    );
    assert.ok(
      messages.some((m) => m.ruleId === "no-restricted-imports"),
      `expected no-restricted-imports, got: ${JSON.stringify(messages)}`,
    );
  });

  it("forbids unallowlisted useEffect, setTimeout, and setInterval calls", async () => {
    const messages = await lintSnippet(
      "app/unapproved.tsx",
      [
        'import { useEffect } from "react";',
        "export function Demo() {",
        "  useEffect(() => {}, []);",
        "  setTimeout(() => {}, 10);",
        "  window.setInterval(() => {}, 10);",
        "  return null;",
        "}",
      ].join("\n"),
    );
    const hits = messages.filter(
      (m) => m.ruleId === "haystack/no-unapproved-effects-or-timers",
    );
    assert.equal(hits.length, 3);
  });

  it("allows calls within cap and rejects calls exceeding cap in allowlisted files", async () => {
    const messages = await lintSnippet(
      "app/sector-table.tsx",
      [
        'import { useEffect } from "react";',
        "export function SectorTable() {",
        "  useEffect(() => {}, []);",
        "  useEffect(() => {}, []);",
        "  return null;",
        "}",
      ].join("\n"),
    );
    const hits = messages.filter(
      (m) => m.ruleId === "haystack/no-unapproved-effects-or-timers",
    );
    assert.equal(hits.length, 1);
    assert.match(hits[0].message, /exceeds allowlist cap \(1\)/);
  });
});
