#!/usr/bin/env python3
"""
NextJS Tree-sitter Indexer
Usage: python indexer.py [project_root] [-o output.json]
"""

import json
import os
import sys
from pathlib import Path

try:
    import tree_sitter_javascript as tsjs
    import tree_sitter_typescript as tsts
    from tree_sitter import Language, Parser
except ImportError:
    print("pip install tree-sitter tree-sitter-javascript tree-sitter-typescript")
    sys.exit(1)

try:
    import tree_sitter_css as tscss
    CSS_LANG = Language(tscss.language())
    HAS_CSS = True
except ImportError:
    HAS_CSS = False
    print("CSS support disabled. pip install tree-sitter-css")

JS_LANG  = Language(tsjs.language())
TS_LANG  = Language(tsts.language_typescript())
TSX_LANG = Language(tsts.language_tsx())

EXT_MAP = {
    ".js":  JS_LANG,
    ".jsx": JS_LANG,
    ".mjs": JS_LANG,
    ".ts":  TS_LANG,
    ".tsx": TSX_LANG,
}

if HAS_CSS:
    EXT_MAP[".css"]  = CSS_LANG
    EXT_MAP[".scss"] = CSS_LANG

SKIP_DIRS = {"node_modules", ".next", ".git", "dist", "build", "out", ".turbo", "coverage"}


# ── CSS ────────────────────────────────────────────────────────────────────────

def parse_css_file(path: Path) -> dict:
    source = path.read_bytes()
    tree = Parser(CSS_LANG).parse(source)
    symbols = []

    def text(node):
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add(kind, name, node):
        symbols.append({
            "kind":       kind,
            "name":       name,
            "start_line": node.start_point[0] + 1,
            "end_line":   node.end_point[0] + 1,
            "start_byte": node.start_byte,
            "end_byte":   node.end_byte,
        })

    def walk(node):
        t = node.type

        if t == "rule_set":
            sel = node.child_by_field_name("selectors") or next(
                (c for c in node.children if c.type == "selectors"), None
            )
            if sel:
                add("selector", text(sel).strip(), node)

        elif t == "keyframes_statement":
            name_node = next((c for c in node.children if c.type == "keyframes_name"), None)
            if name_node:
                add("keyframe", text(name_node).strip(), node)

        elif t == "declaration":
            prop = node.child_by_field_name("property") or next(
                (c for c in node.children if c.type == "property_name"), None
            )
            if prop:
                name = text(prop).strip()
                if name.startswith("--"):
                    add("variable", name, node)

        for child in node.children:
            walk(child)

    walk(tree.root_node)

    return {
        "path":       str(path),
        "language":   path.suffix.lstrip("."),
        "symbols":    symbols,
        "imports":    [],
        "has_errors": tree.root_node.has_error,
    }


# ── JS/TS ──────────────────────────────────────────────────────────────────────

def parse_js_file(path: Path) -> dict:
    lang = EXT_MAP.get(path.suffix.lower())
    source = path.read_bytes()
    tree = Parser(lang).parse(source)
    symbols = []
    imports = []

    def text(node):
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_symbol(kind, name_node, scope_node):
        symbols.append({
            "kind":       kind,
            "name":       text(name_node),
            "start_line": scope_node.start_point[0] + 1,
            "end_line":   scope_node.end_point[0] + 1,
            "start_byte": scope_node.start_byte,
            "end_byte":   scope_node.end_byte,
        })

    def walk(node):
        t = node.type

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                add_symbol("function", name_node, node)

        elif t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                add_symbol("class", name_node, node)

        elif t == "variable_declarator":
            val = node.child_by_field_name("value")
            if val and val.type in ("arrow_function", "function_expression"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    add_symbol("function", name_node, val)

        elif t == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                add_symbol("type", name_node, node)

        elif t == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                add_symbol("interface", name_node, node)

        elif t == "import_statement":
            src = node.child_by_field_name("source")
            if src:
                imports.append({
                    "from":       text(src).strip("\"'"),
                    "start_line": node.start_point[0] + 1,
                    "end_line":   node.end_point[0] + 1,
                    "start_byte": node.start_byte,
                    "end_byte":   node.end_byte,
                })

        for child in node.children:
            walk(child)

    walk(tree.root_node)

    return {
        "path":       str(path),
        "language":   path.suffix.lstrip("."),
        "symbols":    symbols,
        "imports":    imports,
        "has_errors": tree.root_node.has_error,
    }


# ── Router ─────────────────────────────────────────────────────────────────────

def parse_file(path: Path) -> dict:
    if path.suffix.lower() in (".css", ".scss") and HAS_CSS:
        return parse_css_file(path)
    return parse_js_file(path)


# ── Walker ─────────────────────────────────────────────────────────────────────

def index_project(root: Path) -> list[dict]:
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in EXT_MAP:
                try:
                    results.append(parse_file(fpath))
                except Exception as e:
                    results.append({"path": str(fpath), "error": str(e)})
    return results


# ── Entry point ────────────────────────────────────────────────────────────────

def run_indexer(root: str = ".", output: str = "ts_index.json") -> dict:
    root_path = Path(root).resolve()
    print(f"Indexing {root_path} ...")

    files = index_project(root_path)

    out = {"root": str(root_path), "file_count": len(files), "files": files}
    Path(output).write_text(json.dumps(out, indent=2), encoding="utf-8")

    total_symbols = sum(len(f.get("symbols", [])) for f in files)
    print(f"Done — {len(files)} files, {total_symbols} symbols → {output}")

    return out