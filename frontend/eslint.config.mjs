import path from "node:path";
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export const COMMENT_POLICY = {
  "LICENSE_RE": {
    "pattern": "spdx-license-identifier:|copyright|licensed under|all rights reserved|permission is hereby granted",
    "flags": "i"
  },
  "PRETTIER_IGNORE_RE": {
    "pattern": "^\\s*prettier-ignore(?:-(?:start|end))?(?:\\s*:.*)?$",
    "flags": "i"
  },
  "LINK_OR_ISSUE_RE": {
    "pattern": "(?:^|[^\\w&])#[1-9]\\d*\\b|https?://\\S+",
    "flags": "i"
  },
  "PHASE_COMMENT_RE": {
    "pattern": "^\\s*(?:[-*]\\s*)?(?:(?:phase|step)\\s+\\d+(?:\\s*[:.\\-\\u2014\\u2013]|\\s|$)|(?:arrange|act|assert)(?:\\s*(?:,|&|/)\\s*(?:arrange|act|assert))*(?:\\s*[:.\\-\\u2014\\u2013]|\\s*$))",
    "flags": "i"
  },
  "BANNER_DIVIDER_RE": {
    "pattern": "^\\s*(?:-{3,}|={3,})|(?:-{3,}|={3,})\\s*$|^\\s*[-=*~]{4,}\\s*$",
    "flags": ""
  },
  "PROSE_PREFIX_RE": {
    "pattern": "^\\([a-zA-Z0-9]+\\)\\s+",
    "flags": ""
  },
  "JS_CODE_PATTERNS": [
    {
      "pattern": "^(?:export\\s+(?:default\\s+)?)?(?:(?:const|let|var)\\s+[A-Za-z_$][\\w$]*(?:\\s*=|\\s*:[^=]*=)|(?:async\\s+)?function\\*?\\s+[A-Za-z_$][\\w$]*\\s*[<(]|type\\s+[A-Za-z_$][\\w$]*\\s*[=<]|(?:class|interface|enum)\\s+[A-Za-z_$][\\w$]*(?:\\s*[{<]|\\s+(?:extends|implements)\\b))",
      "flags": ""
    },
    {
      "pattern": "^import\\s+(?:type\\s+)?(?:[\\w*{}\\s,]+\\s+from\\s+)?[\"'`][^\"'`]+[\"'`]\\s*;?$|^import\\s*\\([\"'`]|^export\\s+(?:\\*|\\{[^}]*\\}|default\\s+[\\w({])",
      "flags": ""
    },
    {
      "pattern": "^(?:if|else\\s+if|for|while|switch|catch)\\s*\\([^)]*\\)\\s*\\{?\\s*$|^(?:else|try|finally|do)\\s*\\{\\s*$",
      "flags": ""
    },
    {
      "pattern": "^(?:return;\\s*$|return\\s+(?:.*[\\w)\\]}'\"`];|\\(?[A-Za-z_$][\\w$.]*\\(.*\\)|\\{.*\\}|\\[.*\\]|<[A-Za-z/].*>)\\s*$|throw\\s+(?:new\\s+[\\w$.]+\\s*\\(|.*;\\s*$))",
      "flags": ""
    },
    {
      "pattern": "^(?:this\\.|[A-Za-z_$][\\w$.]*)\\s*(?:\\+|-|\\*|/|&&|\\|\\||\\?\\?)?=\\s*[^=].*;\\s*$",
      "flags": ""
    },
    {
      "pattern": "^[}\\])]+;?\\s*$",
      "flags": ""
    },
    {
      "pattern": "^<[A-Za-z][A-Za-z0-9.]*(?:\\s+[^>]*)?/?>\\s*;?\\s*$|^</[A-Za-z][A-Za-z0-9.]*>\\s*;?\\s*$|^<>\\s*$|^</>\\s*$",
      "flags": ""
    }
  ],
  "JS_CALL_PREFIX_RE": {
    "pattern": "^(?:await\\s+)?[A-Za-z_$][\\w$.]*(?:\\?\\.)?\\(",
    "flags": ""
  },
  "TS_IGNORE_RE": {
    "pattern": "@ts-(?:ignore|nocheck)\\b",
    "flags": ""
  },
  "TS_EXPECT_ERROR_RE": {
    "pattern": "@ts-expect-error\\b",
    "flags": ""
  },
  "VALID_TS_EXPECT_ERROR_RE": {
    "pattern": "@ts-expect-error\\s+(?:TS(?:\\(\\d+\\)|\\d+)|@[A-Za-z0-9_/-]+|[A-Za-z0-9_]+(?:[-/.][A-Za-z0-9_]+)+)(?:\\s*,\\s*(?:TS(?:\\(\\d+\\)|\\d+)|@[A-Za-z0-9_/-]+|[A-Za-z0-9_]+(?:[-/.][A-Za-z0-9_]+)+))*\\s+--\\s+\\S",
    "flags": ""
  },
  "ESLINT_DISABLE_RE": {
    "pattern": "\\beslint-disable(?:-next-line|-line)?\\b",
    "flags": ""
  },
  "VALID_ESLINT_DISABLE_RE": {
    "pattern": "\\beslint-disable(?:-next-line|-line)?\\s+[A-Za-z0-9_/@.-]+(?:\\s*,\\s*[A-Za-z0-9_/@.-]+)*\\s+--\\s+\\S",
    "flags": ""
  },
  "CONSTRAINT_CASE_SENSITIVE_RE": {
    "pattern": "\\bIMPORTANT\\b",
    "flags": ""
  },
  "CONSTRAINT_CASE_INSENSITIVE_RE": {
    "pattern": "\\b(?:do\\s+not\\s+remove|don['\\u2019]?t\\s+remove|too\\s+risky|fine\\s+for\\s+now)\\b",
    "flags": "i"
  }
};

const compilePolicyRe = (spec) => new RegExp(spec.pattern, spec.flags);

const LICENSE_RE = compilePolicyRe(COMMENT_POLICY.LICENSE_RE);
const PRETTIER_IGNORE_RE = compilePolicyRe(COMMENT_POLICY.PRETTIER_IGNORE_RE);
const LINK_OR_ISSUE_RE = compilePolicyRe(COMMENT_POLICY.LINK_OR_ISSUE_RE);
const PHASE_COMMENT_RE = compilePolicyRe(COMMENT_POLICY.PHASE_COMMENT_RE);
const BANNER_DIVIDER_RE = compilePolicyRe(COMMENT_POLICY.BANNER_DIVIDER_RE);
const PROSE_PREFIX_RE = compilePolicyRe(COMMENT_POLICY.PROSE_PREFIX_RE);
const JS_CODE_PATTERNS = COMMENT_POLICY.JS_CODE_PATTERNS.map(compilePolicyRe);
const JS_CALL_PREFIX_RE = compilePolicyRe(COMMENT_POLICY.JS_CALL_PREFIX_RE);
const TS_IGNORE_RE = compilePolicyRe(COMMENT_POLICY.TS_IGNORE_RE);
const TS_EXPECT_ERROR_RE = compilePolicyRe(COMMENT_POLICY.TS_EXPECT_ERROR_RE);
const VALID_TS_EXPECT_ERROR_RE = compilePolicyRe(
  COMMENT_POLICY.VALID_TS_EXPECT_ERROR_RE,
);
const ESLINT_DISABLE_RE = compilePolicyRe(COMMENT_POLICY.ESLINT_DISABLE_RE);
const VALID_ESLINT_DISABLE_RE = compilePolicyRe(
  COMMENT_POLICY.VALID_ESLINT_DISABLE_RE,
);
const CONSTRAINT_CASE_SENSITIVE_RE = compilePolicyRe(
  COMMENT_POLICY.CONSTRAINT_CASE_SENSITIVE_RE,
);
const CONSTRAINT_CASE_INSENSITIVE_RE = compilePolicyRe(
  COMMENT_POLICY.CONSTRAINT_CASE_INSENSITIVE_RE,
);

function isCompleteJsCall(text) {
  const match = JS_CALL_PREFIX_RE.exec(text);
  if (!match) {
    return false;
  }
  let idx = match[0].length - 1;
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (; idx < text.length; idx += 1) {
    const ch = text[idx];
    if (quote !== null) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === quote) {
        quote = null;
      }
      continue;
    }
    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
    } else if (ch === "(") {
      depth += 1;
    } else if (ch === ")") {
      depth -= 1;
      if (depth === 0) {
        return /^\s*;?\s*$/.test(text.slice(idx + 1));
      }
    }
  }
  return false;
}

function isJsCommentedCodeLine(line) {
  const trimmed = line.trim();
  if (!trimmed || PROSE_PREFIX_RE.test(trimmed)) {
    return false;
  }
  if (JS_CODE_PATTERNS.some((pattern) => pattern.test(trimmed))) {
    return true;
  }
  return isCompleteJsCall(trimmed);
}

function isJSDocComment(comment) {
  return (
    comment.type === "Block" &&
    comment.value.startsWith("*") &&
    !comment.value.startsWith("**") &&
    comment.value !== "*"
  );
}

function extractCommentLines(comment) {
  if (comment.type === "Line") {
    return [
      {
        lineNo: comment.loc.start.line,
        loc: comment.loc,
        body: comment.value.trim(),
      },
    ];
  }
  const isJSDoc = isJSDocComment(comment);
  const rawLines = comment.value.split(/\r?\n/);
  return rawLines.map((rawLine, index) => {
    let cleaned = rawLine;
    if (index === 0) {
      cleaned = isJSDoc
        ? cleaned.replace(/^\*/, "")
        : cleaned.replace(/^\*+\s*/, "");
    } else if (index > 0) {
      cleaned = cleaned.replace(/^\s*\*?\s?/, "");
    }
    const lineNo = comment.loc.start.line + index;
    const startCol = index === 0 ? comment.loc.start.column : 0;
    const endCol =
      index === rawLines.length - 1 ? comment.loc.end.column : rawLine.length;
    return {
      lineNo,
      loc: {
        start: { line: lineNo, column: startCol },
        end: { line: lineNo, column: Math.max(startCol, endCol) },
      },
      body: cleaned.trim(),
    };
  });
}

function buildCommentSpans(comments, sourceLines) {
  const spans = [];
  for (const comment of comments) {
    if (comment.type === "Shebang") {
      continue;
    }
    if (
      comment.type === "Line" &&
      comment.loc.start.line === 1 &&
      comment.loc.start.column === 0 &&
      (sourceLines[0] || "").startsWith("#!")
    ) {
      continue;
    }
    const extracted = extractCommentLines(comment);
    const prev = spans[spans.length - 1];
    if (
      comment.type === "Line" &&
      prev &&
      prev.style === "line" &&
      comment.loc.start.line === prev.endLine + 1 &&
      comment.loc.start.column === prev.column &&
      (sourceLines[comment.loc.start.line - 1] || "")
        .slice(0, comment.loc.start.column)
        .trim() === ""
    ) {
      prev.endLine = comment.loc.end.line;
      prev.lines.push(...extracted);
      continue;
    }
    spans.push({
      style: isJSDocComment(comment)
        ? "jsdoc"
        : comment.type === "Block"
          ? "block"
          : "line",
      startLine: comment.loc.start.line,
      endLine: comment.loc.end.line,
      column: comment.loc.start.column,
      lines: extracted,
    });
  }
  return spans;
}

function checkUnscopedSuppressionLine(line) {
  if (TS_IGNORE_RE.test(line.body)) {
    return "[unscoped-suppression] @ts-ignore and @ts-nocheck are forbidden; use @ts-expect-error <code-or-rule> -- <rationale>.";
  }
  if (
    TS_EXPECT_ERROR_RE.test(line.body) &&
    !VALID_TS_EXPECT_ERROR_RE.test(line.body)
  ) {
    return "[unscoped-suppression] @ts-expect-error must include a rule or error code and `-- <rationale>`.";
  }
  if (
    ESLINT_DISABLE_RE.test(line.body) &&
    !VALID_ESLINT_DISABLE_RE.test(line.body)
  ) {
    return "[unscoped-suppression] eslint-disable must name rule(s) and `-- <rationale>`.";
  }
  return null;
}

const RULE_POLICIES = [
  {
    respectsLicense: false,
    respectsJSDoc: false,
    respectsLinkExemption: false,
    checkLine: checkUnscopedSuppressionLine,
  },
  {
    respectsLicense: true,
    respectsJSDoc: true,
    respectsLinkExemption: false,
    checkLine: (line) =>
      BANNER_DIVIDER_RE.test(line.body)
        ? "[banner-divider] Banner divider comments are forbidden."
        : null,
  },
  {
    respectsLicense: true,
    respectsJSDoc: true,
    respectsLinkExemption: false,
    checkLine: (line) =>
      PHASE_COMMENT_RE.test(line.body)
        ? "[phase-comment] Phase-narrating test comments are forbidden."
        : null,
  },
  {
    respectsLicense: true,
    respectsJSDoc: true,
    respectsLinkExemption: false,
    checkLine: (line) =>
      isJsCommentedCodeLine(line.body)
        ? "[commented-code] Commented-out code is forbidden."
        : null,
  },
  {
    respectsLicense: true,
    respectsJSDoc: true,
    respectsLinkExemption: true,
    checkLine: (line) =>
      CONSTRAINT_CASE_SENSITIVE_RE.test(line.body) ||
      CONSTRAINT_CASE_INSENSITIVE_RE.test(line.body)
        ? "[unlinked-constraint-marker] Constraint markers must cite an issue (#123) or external specification URL."
        : null,
  },
];

function evaluateSpan(span) {
  const activeLines = span.lines.filter(
    (line) => !PRETTIER_IGNORE_RE.test(line.body),
  );
  if (activeLines.length === 0) {
    return [];
  }
  const bodyText = activeLines.map((line) => line.body).join("\n");
  const isLicense = span.startLine <= 15 && LICENSE_RE.test(bodyText);
  const isJSDoc = span.style === "jsdoc";
  const hasLink = LINK_OR_ISSUE_RE.test(bodyText);
  const activePolicies = RULE_POLICIES.filter(
    (policy) =>
      !(policy.respectsLicense && isLicense) &&
      !(policy.respectsJSDoc && isJSDoc) &&
      !(policy.respectsLinkExemption && hasLink),
  );
  const violations = [];
  for (const line of activeLines) {
    for (const policy of activePolicies) {
      const message = policy.checkLine(line);
      if (message) {
        violations.push({ loc: line.loc, message });
        break;
      }
    }
  }
  return violations;
}

const noCommentsPlugin = {
  rules: {
    "no-bad-comments": {
      meta: {
        type: "problem",
        docs: {
          description: "Disallow commented-out code, phase narration, banner dividers, unscoped suppressions, and unlinked constraint markers.",
        },
        schema: [],
      },
      create(context) {
        return {
          Program() {
            const sourceCode = context.sourceCode;
            const spans = buildCommentSpans(
              sourceCode.getAllComments(),
              sourceCode.lines,
            );
            for (const span of spans) {
              for (const violation of evaluateSpan(span)) {
                context.report(violation);
              }
            }
          },
        };
      },
    },
  },
};

export const EFFECT_AND_TIMER_ALLOWLIST = {
  "app/analyze-page.tsx": { useEffect: 2, setTimeout: 0, setInterval: 0 },
  "app/screen/page.tsx": { useEffect: 2, setTimeout: 0, setInterval: 0 },
  "app/sector-table.tsx": { useEffect: 1, setTimeout: 0, setInterval: 0 },
  "app/components/google-analytics.tsx": {
    useEffect: 1,
    setTimeout: 0,
    setInterval: 0,
  },
  "app/hooks/use-elapsed-ms.ts": { useEffect: 1, setTimeout: 0, setInterval: 1 },
};

const ZERO_EFFECT_TIMER_BUDGET = {
  useEffect: 0,
  setTimeout: 0,
  setInterval: 0,
};

function classifyEffectOrTimerCall(node) {
  const { callee } = node;
  if (callee.type === "Identifier") {
    if (
      callee.name === "useEffect" ||
      callee.name === "setTimeout" ||
      callee.name === "setInterval"
    ) {
      return callee.name;
    }
    return null;
  }
  if (
    callee.type === "MemberExpression" &&
    !callee.computed &&
    callee.object.type === "Identifier" &&
    callee.property.type === "Identifier"
  ) {
    if (callee.object.name === "React" && callee.property.name === "useEffect") {
      return "useEffect";
    }
    if (
      (callee.object.name === "window" || callee.object.name === "globalThis") &&
      (callee.property.name === "setTimeout" ||
        callee.property.name === "setInterval")
    ) {
      return callee.property.name;
    }
  }
  return null;
}

const haystackPlugin = {
  rules: {
    "no-unapproved-effects-or-timers": {
      meta: {
        type: "problem",
        docs: {
          description:
            "Enforce explicit per-file caps on useEffect, setTimeout, and setInterval calls.",
        },
        schema: [],
      },
      create(context) {
        const relPath = path
          .relative(context.cwd, context.filename)
          .replace(/\\/g, "/");
        const budget =
          EFFECT_AND_TIMER_ALLOWLIST[relPath] ?? ZERO_EFFECT_TIMER_BUDGET;
        const counts = { useEffect: 0, setTimeout: 0, setInterval: 0 };

        return {
          CallExpression(node) {
            const kind = classifyEffectOrTimerCall(node);
            if (!kind) return;
            counts[kind] += 1;
            const limit = budget[kind];
            if (counts[kind] > limit) {
              context.report({
                node,
                message:
                  limit === 0
                    ? `${kind} is not allowlisted in ${relPath}; prefer state transitions, server/pure helpers, or AbortSignal.timeout.`
                    : `${kind} count (${counts[kind]}) exceeds allowlist cap (${limit}) in ${relPath}.`,
              });
            }
          },
        };
      },
    },
  },
};

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{js,jsx,mjs,cjs,ts,tsx,mts,cts}"],
    plugins: {
      "no-comments": noCommentsPlugin,
      haystack: haystackPlugin,
    },
    rules: {
      "no-comments/no-bad-comments": "error",
      "haystack/no-unapproved-effects-or-timers": "error",
    },
  },
  {
    files: ["lib/**/*.{js,jsx,mjs,cjs,ts,tsx,mts,cts}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "react",
              message:
                "frontend/lib/ must remain framework-free; do not import react.",
            },
            {
              name: "react-dom",
              message:
                "frontend/lib/ must remain framework-free; do not import react-dom.",
            },
            {
              name: "next",
              message:
                "frontend/lib/ must remain framework-free; do not import next.",
            },
          ],
          patterns: [
            {
              group: ["react/*", "react-dom/*", "next/*"],
              message:
                "frontend/lib/ must remain framework-free; do not import react or next.",
            },
          ],
        },
      ],
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
