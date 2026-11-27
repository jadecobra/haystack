"""Enforce no-comments lint rules across backend, frontend, longmuch, and scripts."""

from __future__ import annotations

import ast
import bisect
import io
import json
import re
import subprocess
import tokenize
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("backend", "frontend", "longmuch", "scripts")
ESLINT_CONFIG_PATH = ROOT / "frontend" / "eslint.config.mjs"
ESLINT_BIN_PATH = ROOT / "frontend" / "node_modules" / ".bin" / "eslint"


class Language(StrEnum):
    PYTHON = "python"
    JS_TS = "js_ts"
    SHELL = "shell"


class CommentStyle(StrEnum):
    HASH = "hash"
    LINE = "line"
    BLOCK = "block"
    JSDOC = "jsdoc"
    SHEBANG = "shebang"


class RuleId(StrEnum):
    PHASE_COMMENT = "phase-comment"
    BANNER_DIVIDER = "banner-divider"
    COMMENTED_CODE = "commented-code"
    UNSCOPED_SUPPRESSION = "unscoped-suppression"
    UNLINKED_CONSTRAINT_MARKER = "unlinked-constraint-marker"


@dataclass(frozen=True)
class CommentLine:
    line_no: int
    column: int
    raw: str
    body: str


@dataclass(frozen=True)
class CommentSpan:
    path: str
    language: Language
    style: CommentStyle
    start_line: int
    end_line: int
    column: int
    lines: tuple[CommentLine, ...]


@dataclass(frozen=True)
class Violation:
    path: str
    line_no: int
    rule: RuleId
    message: str
    snippet: str


@dataclass(frozen=True)
class RulePolicy:
    rule_id: RuleId
    respects_license: bool
    respects_jsdoc: bool
    respects_link_exemption: bool
    message: str
    check_line: Callable[[CommentLine, Language], bool]


def _load_shared_comment_policy() -> dict[str, Any]:
    text = ESLINT_CONFIG_PATH.read_text(encoding="utf-8")
    marker = "export const COMMENT_POLICY ="
    start = text.index("{", text.index(marker) + len(marker))
    return json.JSONDecoder().raw_decode(text, start)[0]


def _compile_re(spec: dict[str, str]) -> re.Pattern[str]:
    return re.compile(spec["pattern"], re.IGNORECASE if "i" in spec.get("flags", "") else 0)


SHARED_POLICY = _load_shared_comment_policy()
POLICY_RE: dict[str, re.Pattern[str]] = {
    k: _compile_re(v) for k, v in SHARED_POLICY.items() if isinstance(v, dict)
}
POLICY_PATTERN_LISTS: dict[str, tuple[re.Pattern[str], ...]] = {
    k: tuple(_compile_re(x) for x in v) for k, v in SHARED_POLICY.items() if isinstance(v, list)
}
EXTENSION_LANGUAGE = {
    ".py": Language.PYTHON, ".ts": Language.JS_TS, ".tsx": Language.JS_TS,
    ".js": Language.JS_TS, ".cjs": Language.JS_TS, ".mjs": Language.JS_TS, ".sh": Language.SHELL,
}
NOQA_RE = re.compile(r"^\s*(?:(?:flake8|ruff):\s*)?noqa(?:\b|:)")
VALID_NOQA_RE = re.compile(r"^\s*(?:(?:flake8|ruff):\s*)?noqa:\s*[A-Z]{1,6}\d+(?:\s*,\s*[A-Z]{1,6}\d+)*\s+-{1,2}\s+\S")
TYPE_IGNORE_RE = re.compile(r"^\s*type:\s*ignore\b")
VALID_TYPE_IGNORE_RE = re.compile(r"^\s*type:\s*ignore\[\s*[A-Za-z0-9_.-]+(?:\s*,\s*[A-Za-z0-9_.-]+)*\s*\]\s+-{1,2}\s+\S")
SHELL_CODE_PATTERNS = (
    re.compile(r"^(?:local|export|readonly|declare|typeset)\s+[A-Za-z_][A-Za-z0-9_]*="),
    re.compile(r"^(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{"),
    re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(?:[\"'$({/\w]|\S)\S*$"),
    re.compile(r"^(?:if|elif)\s+(?:\[\[?|test\b)|^for\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+|^while\s+|^case\s+.+\s+in\b|^(?:fi|done|esac)\s*;?\s*$"),
    re.compile(r"^(?:source|\.)\s+\S+$|^exit\s+\d+$|^echo\s+[\"']"),
    re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*\([^;\n]*\)\s*;\s*$"),
    re.compile(r"^[}\])]+;?\s*$"),
)
REGEX_PREFIX_KEYWORDS = frozenset({
    "return", "throw", "case", "delete", "void", "typeof", "in", "instanceof",
    "new", "else", "do", "yield", "await", "export", "default", "extends", "implements", "of",
})
CONTROL_FLOW_PAREN_KEYWORDS = frozenset({"if", "while", "for", "switch", "catch"})
PYTHON_NON_NONE_BUILTINS = frozenset({
    "int", "str", "float", "bool", "bytes", "bytearray", "object", "Any", "Self", "Never",
    "Literal", "Final", "ClassVar", "Callable", "Iterable", "Iterator", "Sequence",
    "Mapping", "MutableMapping", "list", "dict", "set", "frozenset", "tuple", "Path",
})
PYTHON_STATEMENT_NODES: tuple[type[ast.stmt], ...] = (
    ast.Import, ast.ImportFrom, ast.Return, ast.Raise, ast.Assert, ast.Delete,
    ast.Assign, ast.AugAssign, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try,
    ast.Pass, ast.Break, ast.Continue, ast.Global, ast.Nonlocal,
    *((ast.Match,) if hasattr(ast, "Match") else ()),
)
SHELL_COMMENT_DELIMS = frozenset(" \t;&|(){}")


def _group_adjacent_line_comments(
    path: str, language: Language, items: list[tuple[CommentStyle, int, int, str, str, bool]],
) -> tuple[CommentSpan, ...]:
    spans: list[CommentSpan] = []
    for style, line_no, col, raw, body, is_inline in items:
        cl = CommentLine(line_no, col, raw, body)
        if (
            spans and style in (CommentStyle.HASH, CommentStyle.LINE)
            and spans[-1].style == style and spans[-1].end_line + 1 == line_no
            and spans[-1].column == col and not is_inline
        ):
            p = spans[-1]
            spans[-1] = CommentSpan(p.path, p.language, p.style, p.start_line, line_no, p.column, (*p.lines, cl))
        else:
            spans.append(CommentSpan(path, language, style, line_no, line_no, col, (cl,)))
    return tuple(spans)


def lex_python_comments(source: str, path: str) -> tuple[CommentSpan, ...]:
    lines = source.splitlines()
    items: list[tuple[CommentStyle, int, int, str, str, bool]] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        line_no, col, raw = *tok.start, tok.string
        if line_no == 1 and col == 0 and raw.startswith("#!"):
            items.append((CommentStyle.SHEBANG, line_no, col, raw, raw[2:].strip(), False))
        else:
            lt = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            items.append((CommentStyle.HASH, line_no, col, raw, raw[1:].strip(), bool(lt[:col].strip())))
    return _group_adjacent_line_comments(path, Language.PYTHON, items)


def _offset_to_line_col(starts: list[int], offset: int) -> tuple[int, int]:
    line_idx = max(0, bisect.bisect_right(starts, offset) - 1)
    return line_idx + 1, offset - starts[line_idx]


def _scan_quoted(source: str, start: int, quote: str) -> int:
    idx, n = start + 1, len(source)
    while idx < n:
        ch = source[idx]
        if ch == "\\":
            idx += 2
        elif ch in (quote, "\n"):
            return idx + (1 if ch == quote else 0)
        else:
            idx += 1
    return n


def _scan_regex_literal(source: str, start: int) -> int | None:
    idx, n, in_class = start + 1, len(source), False
    while idx < n:
        ch = source[idx]
        if ch == "\n":
            return None
        if ch == "\\":
            if idx + 1 >= n or source[idx + 1] == "\n":
                return None
            idx += 2
        elif ch == "[":
            in_class, idx = True, idx + 1
        elif ch == "]" and in_class:
            in_class, idx = False, idx + 1
        elif ch == "/" and not in_class:
            idx += 1
            while idx < n and source[idx].isalpha():
                idx += 1
            return idx
        else:
            idx += 1
    return None


def _scan_balanced_angles(source: str, start: int, initial_depth: int) -> int | None:
    pos, depth, n = start, initial_depth, len(source)
    while pos < n:
        ch = source[pos]
        if ch in ("'", '"', "`"):
            pos = _scan_quoted(source, pos, ch)
        elif source.startswith("=>", pos):
            pos += 2
        elif ch == "<":
            depth, pos = depth + 1, pos + 1
        elif ch == ">":
            if depth == 0:
                return pos + 1
            depth, pos = depth - 1, pos + 1
            if initial_depth > 0 and depth == 0:
                return pos
        else:
            pos += 1
    return None


def _can_start_jsx(source: str, lt_idx: int, is_tsx: bool, can_start_expr: bool) -> bool:
    if not is_tsx or not can_start_expr:
        return False
    n, pos = len(source), lt_idx + 1
    if pos >= n or (source[pos] != ">" and not (source[pos].isalpha() or source[pos] in "_$")):
        return False
    if source[pos] == ">":
        return True
    pos += 1
    while pos < n and (source[pos].isalnum() or source[pos] in "_$."):
        pos += 1
    if pos < n and source[pos] == "<":
        after_angles = _scan_balanced_angles(source, pos + 1, 1)
        if after_angles is None:
            return False
        pos = after_angles
    while pos < n and source[pos] in " \t\r\n":
        pos += 1
    if pos >= n:
        return False
    nxt = source[pos]
    if nxt in (",", ";", "?", "&", "|") or (
        source.startswith("extends", pos) and (pos + 7 == n or not (source[pos + 7].isalnum() or source[pos + 7] == "_"))
    ):
        return False
    if nxt == ">":
        after = pos + 1
        while after < n and source[after] in " \t\r\n":
            after += 1
        return not (after < n and source[after] == "(")
    return source.startswith("/>", pos) or nxt.isalpha() or nxt in "{_$"


def _extract_block_lines(raw: str, start_line: int, start_col: int, is_jsdoc: bool) -> tuple[CommentLine, ...]:
    inner = raw[3:-2] if is_jsdoc else raw[2:-2]
    raw_lines, inner_lines = raw.splitlines(), (inner.splitlines() if inner else [""])
    result: list[CommentLine] = []
    for idx, part in enumerate(inner_lines):
        cleaned = re.sub(r"^\*+\s*", "", part) if (idx == 0 and not is_jsdoc) else (
            re.sub(r"^\s*\*?\s?", "", part) if idx > 0 else part
        )
        raw_part = raw_lines[idx] if idx < len(raw_lines) else part
        result.append(CommentLine(start_line + idx, start_col if idx == 0 else 0, raw_part, cleaned.strip()))
    return tuple(result)


def lex_js_ts_comments(source: str, path: str) -> tuple[CommentSpan, ...]:
    n, source_lines = len(source), source.splitlines()
    starts = [0, *(i + 1 for i, c in enumerate(source) if c == "\n")]
    is_tsx = path.lower().endswith((".tsx", ".jsx"))
    spans: list[CommentSpan] = []
    pending: list[tuple[CommentStyle, int, int, str, str, bool]] = []

    def flush() -> None:
        if pending:
            spans.extend(_group_adjacent_line_comments(path, Language.JS_TS, pending))
            pending.clear()

    idx = 0
    if source.startswith("#!"):
        nl = source.find("\n")
        idx = nl if nl != -1 else n
        spans.append(CommentSpan(path, Language.JS_TS, CommentStyle.SHEBANG, 1, 1, 0, (CommentLine(1, 0, source[:idx], source[2:idx].strip()),)))

    stack: list[tuple[str, int]] = []
    paren_stack: list[bool] = []
    last_ident: str | None = None
    can_start_expr = True

    while idx < n:
        mode, ch = (stack[-1][0] if stack else "code"), source[idx]
        if mode == "template":
            if ch == "\\":
                idx += 2
            elif ch == "`":
                stack.pop()
                idx, can_start_expr = idx + 1, False
            elif source.startswith("${", idx):
                stack.append(("template_expr", 1))
                idx, can_start_expr, last_ident = idx + 2, True, None
            else:
                idx += 1
            continue
        if mode == "jsx_text":
            if ch == "{":
                stack.append(("jsx_expr", 1))
                idx, can_start_expr, last_ident = idx + 1, True, None
            elif source.startswith("</", idx):
                end = _scan_balanced_angles(source, idx + 2, 0)
                idx, can_start_expr = (end if end is not None else n), False
                stack.pop()
            elif ch == "<" and idx + 1 < n and (source[idx + 1] == ">" or source[idx + 1].isalpha() or source[idx + 1] in "_$"):
                stack.append(("jsx_tag", 0))
                idx += 1
            else:
                idx += 1
            continue
        if source.startswith("//", idx):
            nl = source.find("\n", idx)
            end = nl if nl != -1 else n
            raw = source[idx:end]
            line_no, col = _offset_to_line_col(starts, idx)
            lt = source_lines[line_no - 1] if 0 < line_no <= len(source_lines) else ""
            pending.append((CommentStyle.LINE, line_no, col, raw, raw[2:].strip(), bool(lt[:col].strip())))
            idx = end
            continue
        if source.startswith("/*", idx):
            flush()
            close = source.find("*/", idx + 2)
            end = close + 2 if close != -1 else n
            raw = source[idx:end]
            line_no, col = _offset_to_line_col(starts, idx)
            is_jsdoc = raw.startswith("/**") and not raw.startswith("/***") and len(raw) >= 5
            bl = _extract_block_lines(raw, line_no, col, is_jsdoc)
            spans.append(CommentSpan(path, Language.JS_TS, CommentStyle.JSDOC if is_jsdoc else CommentStyle.BLOCK, line_no, bl[-1].line_no, col, bl))
            idx = end
            continue
        if mode == "jsx_tag":
            flush()
            depth = stack[-1][1]
            if ch in ("'", '"'):
                idx = _scan_quoted(source, idx, ch)
            elif ch == "{":
                stack.append(("jsx_expr", 1))
                idx, can_start_expr, last_ident = idx + 1, True, None
            elif ch == "<":
                stack[-1], idx = ("jsx_tag", depth + 1), idx + 1
            elif depth > 0:
                if source.startswith("=>", idx):
                    idx += 2
                elif ch == ">":
                    stack[-1], idx = ("jsx_tag", depth - 1), idx + 1
                else:
                    idx += 1
            elif source.startswith("/>", idx):
                stack.pop()
                idx, can_start_expr = idx + 2, False
            elif ch == ">":
                stack[-1], idx = ("jsx_text", 0), idx + 1
            else:
                idx += 1
            continue
        if ch in " \t\r\n":
            idx += 1
            continue
        flush()
        if ch in ("'", '"'):
            idx, can_start_expr, last_ident = _scan_quoted(source, idx, ch), False, None
        elif ch == "`":
            stack.append(("template", 0))
            idx, last_ident = idx + 1, None
        elif ch == "/" and can_start_expr and (regex_end := _scan_regex_literal(source, idx)) is not None:
            idx, can_start_expr, last_ident = regex_end, False, None
        elif ch == "<" and _can_start_jsx(source, idx, is_tsx, can_start_expr):
            frag = source.startswith("<>", idx)
            stack.append(("jsx_text" if frag else "jsx_tag", 0))
            idx, last_ident = idx + (2 if frag else 1), None
        elif ch == "{":
            if stack and stack[-1][0] in ("template_expr", "jsx_expr"):
                stack[-1] = (stack[-1][0], stack[-1][1] + 1)
            idx, can_start_expr, last_ident = idx + 1, True, None
        elif ch == "}":
            if stack and stack[-1][0] in ("template_expr", "jsx_expr"):
                m, d = stack[-1]
                if d == 1:
                    stack.pop()
                    idx, can_start_expr, last_ident = idx + 1, False, None
                    continue
                stack[-1] = (m, d - 1)
            idx, can_start_expr, last_ident = idx + 1, True, None
        elif ch == "(":
            paren_stack.append(last_ident in CONTROL_FLOW_PAREN_KEYWORDS)
            idx, can_start_expr, last_ident = idx + 1, True, None
        elif ch == ")":
            can_start_expr, idx, last_ident = (paren_stack.pop() if paren_stack else False), idx + 1, None
        elif ch.isalpha() or ch in "_$":
            end = idx + 1
            while end < n and (source[end].isalnum() or source[end] in "_$"):
                end += 1
            ident = source[idx:end]
            can_start_expr, last_ident, idx = ident in REGEX_PREFIX_KEYWORDS, ident, end
        elif ch.isdigit():
            end = idx + 1
            while end < n and (source[end].isalnum() or source[end] in "._"):
                end += 1
            can_start_expr, last_ident, idx = False, None, end
        elif source.startswith("++", idx) or source.startswith("--", idx):
            idx, can_start_expr, last_ident = idx + 2, False, None
        else:
            idx, can_start_expr, last_ident = idx + 1, ch != "]", None

    flush()
    return tuple(spans)


def _parse_heredoc_delimiter(source: str, start: int) -> tuple[str, bool, int] | None:
    n = len(source)
    if source.startswith("<<<", start):
        return None
    pos, strip_tabs = start + 2, (start + 2 < n and source[start + 2] == "-")
    if strip_tabs:
        pos += 1
    while pos < n and source[pos] in " \t":
        pos += 1
    chars: list[str] = []
    while pos < n and source[pos] not in " \t\r\n;&|()<>":
        ch = source[pos]
        if ch in ("'", '"'):
            q, pos = ch, pos + 1
            while pos < n and source[pos] not in (q, "\n"):
                chars.append(source[pos])
                pos += 1
            if pos < n and source[pos] == q:
                pos += 1
        elif ch == "\\":
            pos += 1
            if pos < n and source[pos] != "\n":
                chars.append(source[pos])
                pos += 1
        else:
            chars.append(ch)
            pos += 1
    delim = "".join(chars)
    return (delim, strip_tabs, pos) if delim else None


def lex_shell_comments(source: str, path: str) -> tuple[CommentSpan, ...]:
    n, source_lines = len(source), source.splitlines()
    starts = [0, *(i + 1 for i, c in enumerate(source) if c == "\n")]
    items: list[tuple[CommentStyle, int, int, str, str, bool]] = []
    heredocs: list[tuple[str, bool]] = []
    idx = 0
    if source.startswith("#!"):
        nl = source.find("\n")
        idx = nl if nl != -1 else n
        items.append((CommentStyle.SHEBANG, 1, 0, source[:idx], source[2:idx].strip(), False))

    def scan(pos: int, mode: str) -> int:
        depth, is_cmd = (1 if mode == "param" else 0), mode in ("cmd", "subcmd")
        while pos < n:
            ch = source[pos]
            if ch == "\\":
                pos += 2
            elif ch == "'" and mode != "dquote":
                end = source.find("'", pos + 1)
                pos = end + 1 if end != -1 else n
            elif ch == '"':
                if mode == "dquote":
                    return pos + 1
                pos = scan(pos + 1, "dquote")
            elif source.startswith("${", pos):
                pos = scan(pos + 2, "param")
            elif source.startswith("$((", pos):
                pos = scan(pos + 3, "arith")
            elif source.startswith("$(", pos):
                pos = scan(pos + 2, "subcmd")
            elif mode == "param" and ch in "{}":
                depth, pos = depth + (1 if ch == "{" else -1), pos + 1
                if depth == 0:
                    return pos
            elif mode == "arith" and ch in "()":
                if ch == "(":
                    depth, pos = depth + 1, pos + 1
                elif depth > 0:
                    depth, pos = depth - 1, pos + 1
                else:
                    return pos + (2 if source.startswith("))", pos) else 1)
            elif not is_cmd:
                pos += 1
            elif ch == "\n":
                pos += 1
                while heredocs and pos < n:
                    delim, strip_tabs = heredocs.pop(0)
                    while pos < n:
                        nl = source.find("\n", pos)
                        end = nl if nl != -1 else n
                        line_str = source[pos:end].rstrip("\r")
                        pos = end + 1 if nl != -1 else n
                        if (line_str.lstrip("\t") if strip_tabs else line_str) == delim:
                            break
            elif source.startswith("$'", pos):
                pos = _scan_quoted(source, pos + 1, "'")
            elif source.startswith("((", pos):
                pos = scan(pos + 2, "arith")
            elif source.startswith("$#", pos):
                pos += 2
            elif mode == "subcmd" and ch in "()":
                if ch == "(":
                    depth, pos = depth + 1, pos + 1
                elif depth == 0:
                    return pos + 1
                else:
                    depth, pos = depth - 1, pos + 1
            elif source.startswith("<<", pos) and (parsed := _parse_heredoc_delimiter(source, pos)) is not None:
                heredocs.append((parsed[0], parsed[1]))
                pos = parsed[2]
            elif ch == "#":
                line_no, col = _offset_to_line_col(starts, pos)
                prev_ch = source[pos - 1] if pos > 0 else "\n"
                if col == 0 or prev_ch in SHELL_COMMENT_DELIMS:
                    nl = source.find("\n", pos)
                    end = nl if nl != -1 else n
                    raw = source[pos:end]
                    lt = source_lines[line_no - 1] if 0 < line_no <= len(source_lines) else ""
                    items.append((CommentStyle.HASH, line_no, col, raw, raw[1:].strip(), bool(lt[:col].strip())))
                    pos = end
                else:
                    pos += 1
            else:
                pos += 1
        return n

    scan(idx, "cmd")
    return _group_adjacent_line_comments(path, Language.SHELL, items)


def _is_valid_python_ann_assign(node: ast.AnnAssign) -> bool:
    if node.value is not None:
        return True
    if not isinstance(node.target, ast.Name) or not re.match(r"^[a-z_][a-z0-9_]*$", node.target.id):
        return False
    ann = node.annotation
    if isinstance(ann, ast.Subscript) or (isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr)):
        return True
    if isinstance(ann, ast.Name):
        return ann.id in PYTHON_NON_NONE_BUILTINS
    return isinstance(ann, ast.Attribute) and ann.attr in PYTHON_NON_NONE_BUILTINS


def _strip_python_inline_comment(text: str) -> str:
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                return text[: tok.start[1]].rstrip()
    except tokenize.TokenError:
        pass
    return text.rstrip()


def _is_python_commented_code(line: str) -> bool:
    stripped = re.sub(r"\s*\(#\d+\)\s*$", "", line.strip())
    if not stripped or POLICY_RE["PROSE_PREFIX_RE"].match(stripped):
        return False
    candidates = [stripped]
    if stripped.endswith(":"):
        if re.match(r"^try\s*:", stripped):
            candidates.append(f"{stripped}\n    pass\nexcept Exception:\n    pass")
        elif re.match(r"^(?:elif|else)\b", stripped):
            candidates.append(f"if False:\n    pass\n{stripped}\n    pass")
        elif re.match(r"^(?:except|finally)\b", stripped):
            candidates.append(f"try:\n    pass\n{stripped}\n    pass")
        else:
            candidates.append(f"{stripped}\n    pass")
    for candidate in candidates:
        try:
            tree = ast.parse(candidate)
        except SyntaxError:
            continue
        if not tree.body:
            continue
        node = tree.body[-1]
        if isinstance(node, PYTHON_STATEMENT_NODES) or (isinstance(node, ast.AnnAssign) and _is_valid_python_ann_assign(node)):
            return True
        if isinstance(node, ast.Expr):
            val = node.value
            if isinstance(val, ast.Call):
                code_part = _strip_python_inline_comment(stripped)
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*\s+\(", code_part) and code_part.endswith(")"):
                    return True
            elif isinstance(val, ast.Tuple) and stripped.startswith("(") and stripped.endswith(")") and any(
                isinstance(c, ast.BinOp) and isinstance(c.op, ast.BitOr) for c in ast.walk(val)
            ):
                return True
    return False


def _is_complete_js_call(text: str) -> bool:
    match = POLICY_RE["JS_CALL_PREFIX_RE"].match(text)
    if match is None:
        return False
    idx, depth, quote, escaped = match.end() - 1, 0, None, False
    while idx < len(text):
        ch = text[idx]
        if quote is not None:
            escaped = not escaped and ch == "\\"
            if not escaped and ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return bool(re.match(r"^\s*;?\s*$", text[idx + 1 :]))
        idx += 1
    return False


def _is_unscoped_suppression_line(line: CommentLine, language: Language) -> bool:
    body = line.body
    if language in (Language.PYTHON, Language.SHELL) and (
        (NOQA_RE.search(body) and not VALID_NOQA_RE.search(body))
        or (TYPE_IGNORE_RE.search(body) and not VALID_TYPE_IGNORE_RE.search(body))
    ):
        return True
    return bool(
        POLICY_RE["TS_IGNORE_RE"].search(body)
        or (POLICY_RE["TS_EXPECT_ERROR_RE"].search(body) and not POLICY_RE["VALID_TS_EXPECT_ERROR_RE"].search(body))
        or (POLICY_RE["ESLINT_DISABLE_RE"].search(body) and not POLICY_RE["VALID_ESLINT_DISABLE_RE"].search(body))
    )


def _is_commented_code_line(line: CommentLine, language: Language) -> bool:
    if language == Language.PYTHON:
        return _is_python_commented_code(line.body)
    stripped = line.body.strip()
    if not stripped or POLICY_RE["PROSE_PREFIX_RE"].match(stripped):
        return False
    if language == Language.JS_TS:
        return any(p.search(stripped) for p in POLICY_PATTERN_LISTS["JS_CODE_PATTERNS"]) or _is_complete_js_call(stripped)
    return any(p.search(stripped) for p in SHELL_CODE_PATTERNS)


RULE_POLICIES: tuple[RulePolicy, ...] = (
    RulePolicy(RuleId.UNSCOPED_SUPPRESSION, False, False, False, "Unscoped or unannotated lint/type suppression is forbidden.", _is_unscoped_suppression_line),
    RulePolicy(RuleId.BANNER_DIVIDER, True, True, False, "Banner divider comments are forbidden.", lambda line, _: bool(POLICY_RE["BANNER_DIVIDER_RE"].search(line.body))),
    RulePolicy(RuleId.PHASE_COMMENT, True, True, False, "Phase-narrating test comments are forbidden.", lambda line, _: bool(POLICY_RE["PHASE_COMMENT_RE"].search(line.body))),
    RulePolicy(RuleId.COMMENTED_CODE, True, True, False, "Commented-out code is forbidden.", _is_commented_code_line),
    RulePolicy(
        RuleId.UNLINKED_CONSTRAINT_MARKER, True, True, True,
        "Constraint markers must cite an issue (#123) or external specification URL.",
        lambda line, _: bool(POLICY_RE["CONSTRAINT_CASE_SENSITIVE_RE"].search(line.body) or POLICY_RE["CONSTRAINT_CASE_INSENSITIVE_RE"].search(line.body)),
    ),
)


def evaluate_span(span: CommentSpan) -> tuple[Violation, ...]:
    if span.style == CommentStyle.SHEBANG:
        return ()
    active_lines = tuple(line for line in span.lines if not POLICY_RE["PRETTIER_IGNORE_RE"].search(line.body))
    if not active_lines:
        return ()
    body_text = "\n".join(line.body for line in active_lines)
    is_license = span.start_line <= 15 and bool(POLICY_RE["LICENSE_RE"].search(body_text))
    has_link = bool(POLICY_RE["LINK_OR_ISSUE_RE"].search(body_text))
    is_jsdoc = span.style == CommentStyle.JSDOC
    applicable = tuple(
        p for p in RULE_POLICIES
        if not ((p.respects_license and is_license) or (p.respects_jsdoc and is_jsdoc) or (p.respects_link_exemption and has_link))
    )
    violations: list[Violation] = []
    for line in active_lines:
        for policy in applicable:
            if policy.check_line(line, span.language):
                violations.append(Violation(span.path, line.line_no, policy.rule_id, policy.message, line.raw))
                break
    return tuple(violations)


def check_source(source: str, path: str, language: Language | None = None) -> list[Violation]:
    lang = language or EXTENSION_LANGUAGE.get(Path(path).suffix.lower())
    if lang is None:
        return []
    spans = lex_python_comments(source, path) if lang == Language.PYTHON else (
        lex_js_ts_comments(source, path) if lang == Language.JS_TS else lex_shell_comments(source, path)
    )
    return [v for span in spans for v in evaluate_span(span)]


def scan_repository(root: Path = ROOT) -> list[Violation]:
    raw = subprocess.check_output(["git", "ls-files", *SCAN_ROOTS], cwd=root, text=True)
    files = [root / rel for rel in raw.splitlines() if rel and Path(rel).suffix.lower() in EXTENSION_LANGUAGE]
    return [v for fp in files for v in check_source(fp.read_text(encoding="utf-8"), fp.relative_to(root).as_posix())]


def _run_eslint_matrix(cases: list[tuple[str, str, list[RuleId]]]) -> dict[str, Any]:
    node_script = (
        'import { ESLint } from "eslint"; import { COMMENT_POLICY } from "./eslint.config.mjs";\n'
        'const payload = JSON.parse(process.argv[1]); const eslint = new ESLint({ cwd: process.cwd() }); const results = [];\n'
        'for (const item of payload) { const res = await eslint.lintText(item.code, { filePath: item.filePath });\n'
        '  results.push(res[0].messages.filter((m) => m.ruleId === "no-comments/no-bad-comments")\n'
        '    .map((m) => [(/^\\[([a-z-]+)\\]/.exec(m.message) || [])[1] ?? null, m.message])); }\n'
        'process.stdout.write(JSON.stringify({ policy: COMMENT_POLICY, results }));'
    )
    payload = [{"code": code, "filePath": f"lib/parity-case-{i}.{ext}"} for i, (ext, code, _) in enumerate(cases)]
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", node_script, json.dumps(payload)],
        cwd=ROOT / "frontend", capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


class TestRepositoryNoComments(unittest.TestCase):
    def test_tracked_files_have_no_comment_violations(self) -> None:
        violations = scan_repository(ROOT)
        formatted = "\n".join(f"{v.path}:{v.line_no} [{v.rule}] {v.message} -> {v.snippet}" for v in violations)
        self.assertEqual(violations, [], f"Comment violations found:\n{formatted}")


class TestViolationRules(unittest.TestCase):
    def _assert_matrix(self, cases: tuple[tuple[str, list[RuleId], tuple[str, ...]], ...]) -> None:
        for path, expected, samples in cases:
            for sample in samples:
                self.assertEqual([v.rule for v in check_source(sample, path)], expected, f"Mismatch for {path}: {sample!r}")

    def test_phase_and_banner_comments(self) -> None:
        phases = ("Phase 1: seed database", "phase 2 - call endpoint", "Step 1. setup", "step 3: verify", "Arrange", "Act:", "Assert - exact match", "Arrange, Act, Assert")
        banners = ("--- helpers ---------------------------------", "=== section ===", "---------------------------------------------", "=============================================")
        for path, prefix in (("a.py", "#"), ("a.ts", "//"), ("a.sh", "#")):
            self._assert_matrix(((path, [RuleId.PHASE_COMMENT], tuple(f"{prefix} {b}\n" for b in phases)), (path, [RuleId.BANNER_DIVIDER], tuple(f"{prefix} {b}\n" for b in banners))))
        self._assert_matrix((("a.ts", [RuleId.BANNER_DIVIDER], ("/* --- section --- */\n",)), ("a.py", [], ("# Last cash ladder steps. Keep in sync.\n", "# step cannot reach the internal cache.\n"))))

    def test_commented_code_python_js_and_shell(self) -> None:
        self._assert_matrix((
            ("a.py", [RuleId.COMMENTED_CODE], (
                "# import os\n", "# from pathlib import Path\n", "# x = compute_value(1, 2)\n", "# count += 1\n", "# items: list[str] = []\n",
                "# items: list[str]\n", "# count: int\n", "# value: int | None\n", "# value: int | None = None\n", "# return result\n",
                "# raise ValueError('bad')\n", "# assert total == 42\n", "# if flag:\n", "# elif other:\n", "# else:\n", "# for item in items:\n",
                "# def helper(a, b):\n", "# class Widget:\n", "# try:\n", "# except ValueError:\n", "# finally:\n", "# with open('x') as fh:\n",
                "# helper_call(1, 2)\n", "# compute(1, 2)  # old\n", "# (mtime, by_year, daily_latest | None)\n",
            )),
            ("a.py", [], (
                "# (a) Period identity: same fy pick.\n", "# (b) Latest kept restatement for that period.\n", "# (c) Basis-jump intervals from every fact.\n",
                "# AAPL: not mapped\n", "# below: dropped\n", "# job, #21). None locally.\n", "# Prefer USD, then USD/shares variants.\n",
                "# see helper (optional)\n", "# Source: SEC\n", "# Default: None\n", "# Note: Keep\n", "# x: None\n",
            )),
            ("a.tsx", [RuleId.COMMENTED_CODE], (
                "// const total = 42;\n", "// const typed: number = 42;\n", "// let items = [];\n", "// export function run() {\n", "// type Foo = string;\n",
                "// class Foo {\n", "// import { foo } from './bar';\n", "// if (ready) {\n", "// for (const x of list) {\n", "// return null;\n",
                "// throw new Error('boom');\n", "// this.value = 1;\n", "// console.log('debug', value);\n", "// foo(bar(1));\n", "// });\n", "// <Button disabled />\n", "// </div>\n",
            )),
            ("a.ts", [], ("// return early when the cache is cold\n", "// foo(bar) and baz(qux) remain separate\n", "// type check: ok\n", "// class Name: styling\n", "// interface contract: returns null\n", "// function check: must work\n")),
            ("a.sh", [RuleId.COMMENTED_CODE], ("# local count=0\n", '# export PATH="/usr/bin"\n', "# FOO=bar\n", '# if [ -f "$file" ]; then\n', "# for item in a b; do\n", "# fi\n", '# echo "debug"\n', "# exit 1\n")),
            ("a.sh", [], ("# Start a local API and wait for health.\n",)),
        ))

    def test_unscoped_suppressions_and_constraint_markers(self) -> None:
        self._assert_matrix((
            ("a.py", [RuleId.UNSCOPED_SUPPRESSION], (
                "x = 1  # noqa\n", "x = 1  # noqa: BLE001\n", "x = 1  # noqa: BLE001 -\n", "x = 1  # noqa - reason without code\n",
                "x = 1  # ruff: noqa\n", "x = 1  # ruff: noqa: E501\n", "x = 1  # type: ignore\n",
                "x = 1  # type: ignore - reason without code\n", "x = 1  # type: ignore[arg-type]\n", "x = 1  # type: ignore[arg-type] -\n",
            )),
            ("a.py", [], (
                "x = 1  # noqa: BLE001 - fail-soft cache read\n", "x = 1  # noqa: BLE001, S110 - optional dependency\n", "x = 1  # ruff: noqa: E501 - long fixture URL\n",
                "x = 1  # type: ignore[arg-type] - legacy shim\n", "x = 1  # type: ignore[arg-type, return-value] -- third-party stub\n", "# important note in lowercase prose\n",
            )),
            ("a.ts", [RuleId.UNSCOPED_SUPPRESSION], (
                "// @ts-ignore\n", "// @ts-ignore legacy prop\n", "/** @ts-ignore */\n", "// @ts-nocheck\n", "/** @ts-nocheck */\n",
                "// @ts-expect-error\n", "// @ts-expect-error -- missing code\n", "// @ts-expect-error TS2345\n", "// @ts-expect-error missing separator\n",
                "// @ts-expect-error whatever -- reason\n", "/* eslint-disable */\n", "/** eslint-disable */\n", "// eslint-disable-next-line\n",
                "// eslint-disable-line\n", "// eslint-disable-next-line react-hooks/exhaustive-deps\n", "// eslint-disable-next-line -- missing rule name\n", "// @ts-ignore const x = 1;\n",
            )),
            ("a.ts", [], (
                "// @ts-expect-error TS2345 -- third-party type mismatch\n", "// @ts-expect-error TS(2322) -- intentional narrow test input\n",
                "// @ts-expect-error foo-bar -- custom transformer contract\n", "// @ts-expect-error @scope/rule -- typed boundary\n",
                "// eslint-disable-next-line @next/next/no-img-element -- external URL\n", "/* eslint-disable no-console, prefer-const -- CLI script */\n",
            )),
            ("a.py", [RuleId.UNLINKED_CONSTRAINT_MARKER], ("# IMPORTANT: keep ordering\n", "# fine for now\n")),
            ("a.ts", [RuleId.UNLINKED_CONSTRAINT_MARKER], ("// do not remove this timeout\n", "// Don't remove this fallback\n")),
            ("a.sh", [RuleId.UNLINKED_CONSTRAINT_MARKER], ("# too risky to refactor\n",)),
            ("a.ts", [RuleId.PHASE_COMMENT, RuleId.COMMENTED_CODE, RuleId.UNSCOPED_SUPPRESSION], ("// Phase 1: setup\n// const x = 1;\n// @ts-ignore\n",)),
        ))


class TestExemptions(unittest.TestCase):
    def test_shebang_docstring_and_jsdoc_exemptions(self) -> None:
        for code, path in (
            ("#!/usr/bin/env python3\n", "a.py"), ("#!/usr/bin/env node\n", "a.mjs"), ("#!/usr/bin/env bash\n", "a.sh"),
            ('"""Phase 1: docstrings are literals.\n# --- div ---\nIMPORTANT\n"""\n', "a.py"),
            ("/** IMPORTANT contract detail. const x = 1; */\n", "a.ts"), ("/***/\n", "a.ts"),
        ):
            self.assertEqual(check_source(code, path), [], code)
        self.assertEqual(check_source("/*** const x = 1; */\n", "a.ts")[0].rule, RuleId.COMMENTED_CODE)
        self.assertEqual(check_source("/** @ts-ignore */\n", "a.ts")[0].rule, RuleId.UNSCOPED_SUPPRESSION)
        self.assertEqual(check_source("/** eslint-disable */\n", "a.ts")[0].rule, RuleId.UNSCOPED_SUPPRESSION)

    def test_license_prettier_and_link_precedence(self) -> None:
        for code, path in (
            ("// SPDX-License-Identifier: MIT\n// IMPORTANT: do not remove\n", "a.ts"), ("# Copyright 2026 Example Corp. All rights reserved.\n", "a.py"),
            ("// prettier-ignore\nconst x = [1,2];\n", "a.ts"), ("/* prettier-ignore-start */\n", "a.ts"), ("// prettier-ignore: matrix\n", "a.ts"),
            ("# IMPORTANT: keep guard (#123)\n", "a.py"), ("// Do not remove: https://example.com/spec\n", "a.ts"),
            ("# IMPORTANT: preserve ordering\n# Tracked in #123.\n", "a.py"), ("  // Do not remove this retry\n  // See https://example.com/retry\n", "a.ts"),
        ):
            self.assertEqual(check_source(code, path), [], code)
        self.assertEqual([v.rule for v in check_source("// SPDX-License-Identifier: MIT\n// @ts-ignore\n// IMPORTANT: do not remove\n", "a.ts")], [RuleId.UNSCOPED_SUPPRESSION])
        sneaky = check_source("// prettier-ignore\n// @ts-ignore\n// const x = 1;\n", "a.ts")
        self.assertEqual([(v.line_no, v.rule) for v in sneaky], [(2, RuleId.UNSCOPED_SUPPRESSION), (3, RuleId.COMMENTED_CODE)])
        for code, path, rule in (
            ("// @ts-ignore prettier-ignore\n", "a.ts", RuleId.UNSCOPED_SUPPRESSION), ("# Phase 1: setup (#123)\n", "a.py", RuleId.PHASE_COMMENT),
            ("# --- section --- (#123)\n", "a.py", RuleId.BANNER_DIVIDER), ("# x = 1 (#123)\n", "a.py", RuleId.COMMENTED_CODE),
            ("x = 1  # noqa (#123)\n", "a.py", RuleId.UNSCOPED_SUPPRESSION), ("// @ts-ignore https://example.com\n", "a.ts", RuleId.UNSCOPED_SUPPRESSION),
        ):
            self.assertEqual([v.rule for v in check_source(code, path)], [rule])


class TestLexerBoundaries(unittest.TestCase):
    def test_js_strings_templates_regex_and_tsx_generics(self) -> None:
        ts_code = (
            'const url = "https://example.com // not a comment"; const single = \'/* not a comment */\';\n'
            "const tpl = `prefix ${`nested ${a} // inner` + '// str'} suffix // not comment`;\n"
            "const re = /https?:\\/\\//g; const ratio = total / count; const div = (a + b) / (c + d);\n"
            "if (cond) /https?:\\/\\//.test(url); while (cond) /foo\\/\\/bar/.test(url); for (const x of xs) /foo\\/\\/bar/.test(x);\n"
        )
        self.assertEqual(check_source(ts_code, "a.ts"), [])
        self.assertEqual([v.rule for v in check_source(f"{ts_code}// const dead = 1;\n", "a.ts")], [RuleId.COMMENTED_CODE])
        tsx = (
            "const id = <T>(x: T) => x;\nfunction View<T>(items: Array<string>) {\n  return (\n"
            '    <a href="https://example.com">https://example.com // literal jsx text /* not comment */'
            '{"// string inside jsx expr"}<Foo<string>>https://example.com // generic jsx text</Foo<string>>'
            '<Foo<Record<string, () => void>> prop="x" /></a>\n  );\n}\n'
        )
        self.assertEqual(check_source(tsx, "a.tsx"), [])
        tsx_bad = "const id = <T>(x: T) => x;\nfunction View<T>() { // const unused = 1;\n  return <div>{/* const dead = 2; */}<Foo<string>>ok</Foo<string>></div>;\n}\n"
        self.assertEqual([v.rule for v in check_source(tsx_bad, "a.tsx")], [RuleId.COMMENTED_CODE, RuleId.COMMENTED_CODE])

    def test_shell_expansions_arithmetic_and_heredocs(self) -> None:
        sh = (
            '#!/usr/bin/env bash\nset -euo pipefail\necho "${var##pattern}"\necho "count=$#"\necho foo#bar\n'
            'x=$((1 << 4))\n(( x << 2 ))\necho "$((1 << 4))"\necho "$(echo "hello # Phase 1: foo")"\n'
            "python3 - <<'PY'\n# --- this is python inside a heredoc, not shell ---\n# const x = 1;\nprint(\"ok\")\nPY\n"
            "cat <<EOF\n# IMPORTANT inside heredoc body\nEOF\n"
        )
        self.assertEqual(check_source(sh, "a.sh"), [])
        self.assertEqual([v.rule for v in check_source(f"{sh}\n# Phase 1: run script\n", "a.sh")], [RuleId.PHASE_COMMENT])
        self.assertEqual([v.rule for v in check_source('x=$(\n  # Phase 1: inside cmd subst\n  echo "ok"\n)\n', "a.sh")], [RuleId.PHASE_COMMENT])


class TestEslintParity(unittest.TestCase):
    def test_eslint_config_enables_no_bad_comments_at_error(self) -> None:
        config_text = ESLINT_CONFIG_PATH.read_text(encoding="utf-8")
        self.assertIn('"no-comments/no-bad-comments": "error"', config_text)
        self.assertIn("getAllComments()", config_text)

    def test_python_and_eslint_agree_on_shared_matrix(self) -> None:
        raw_matrix: tuple[tuple[str, str, list[RuleId]], ...] = (
            ("ts", "// Phase 1: setup", [RuleId.PHASE_COMMENT]), ("ts", "// Step 2 - execute", [RuleId.PHASE_COMMENT]),
            ("ts", "// Arrange", [RuleId.PHASE_COMMENT]), ("ts", "// --- helpers ---", [RuleId.BANNER_DIVIDER]),
            ("ts", "/* === section === */", [RuleId.BANNER_DIVIDER]), ("ts", "// const oldVal = 1;", [RuleId.COMMENTED_CODE]),
            ("ts", "// return null;", [RuleId.COMMENTED_CODE]), ("ts", "// console.log(x);", [RuleId.COMMENTED_CODE]),
            ("tsx", "// <Button />", [RuleId.COMMENTED_CODE]), ("ts", "// type check: ok", []), ("ts", "// class Name: styling", []),
            ("ts", "// @ts-ignore", [RuleId.UNSCOPED_SUPPRESSION]), ("ts", "// @ts-nocheck", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "/** @ts-ignore */", [RuleId.UNSCOPED_SUPPRESSION]), ("ts", "// @ts-expect-error", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// @ts-expect-error -- missing code", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// @ts-expect-error TS2345", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// @ts-expect-error whatever -- reason", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// eslint-disable-next-line", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// eslint-disable-next-line no-console", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// eslint-disable-next-line -- missing rule", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// IMPORTANT: keep order", [RuleId.UNLINKED_CONSTRAINT_MARKER]),
            ("ts", "// do not remove this", [RuleId.UNLINKED_CONSTRAINT_MARKER]),
            ("ts", "// fine for now", [RuleId.UNLINKED_CONSTRAINT_MARKER]),
            ("ts", "// prettier-ignore\n// @ts-ignore\n// const a = 1;\nexport const b = 1;\n", [RuleId.UNSCOPED_SUPPRESSION, RuleId.COMMENTED_CODE]),
            ("ts", "// @ts-ignore prettier-ignore", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "// SPDX-License-Identifier: MIT\n// @ts-ignore\n// IMPORTANT: keep\nexport const a = 1;\n", [RuleId.UNSCOPED_SUPPRESSION]),
            ("ts", "/*** const x = 1; */", [RuleId.COMMENTED_CODE]), ("ts", "/***/", []),
            ("ts", "// @ts-expect-error TS2345 -- intentional test input", []),
            ("ts", "// eslint-disable-next-line no-console -- CLI entry\nconsole.log(1);\n", []),
            ("ts", "// IMPORTANT: keep order (#123)", []),
            ("ts", "// Do not remove\n// https://example.com/spec\nexport const a = 1;\n", []),
            ("ts", "/** Public contract docs. const a = 1; */", []), ("ts", "// prettier-ignore", []),
            ("ts", 'export const u = "https://example.com // ok";\n', []),
            ("ts", "export const r = /https?:\\/\\//;\nexport const f = (c: boolean) => { if (c) /re/.test(u); };\n", []),
            ("tsx", "export const id = <T>(x: T) => x;\nexport function C() { return <Foo<string>>https://example.com // ok</Foo<string>>; }\n", []),
        )
        matrix = [(ext, s if "\n" in s else f"{s}\nexport const a = 1;\n", exp) for ext, s, exp in raw_matrix]
        for ext, code, expected in matrix:
            self.assertEqual([v.rule for v in check_source(code, f"parity.{ext}", Language.JS_TS)], expected, f"Python mismatch for {code!r}")

        if not ESLINT_BIN_PATH.exists():
            self.skipTest("frontend/node_modules/.bin/eslint is not installed")

        eslint_payload = _run_eslint_matrix(matrix)
        self.assertEqual(eslint_payload["policy"], SHARED_POLICY)
        for (ext, code, expected), eslint_msgs in zip(matrix, eslint_payload["results"], strict=True):
            self.assertEqual(
                [rule_tag for rule_tag, _ in eslint_msgs],
                [rule.value for rule in expected],
                f"ESLint mismatch on .{ext} snippet {code!r}: {eslint_msgs}",
            )
