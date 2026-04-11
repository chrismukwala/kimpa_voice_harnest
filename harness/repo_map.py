"""Repo map — tree-sitter based repository symbol index for LLM context."""

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    from tree_sitter_languages import get_parser as _get_parser
except ImportError:
    _get_parser = None
    log.info("tree-sitter-languages not installed; repo map disabled")

# File extensions to index.
_ALLOWED_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".java",
})

# Map extensions to tree-sitter language names.
_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
}

# Directories to always skip.
_DEFAULT_EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn",
    ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".tox",
    "node_modules",
    "dist", "build", ".eggs",
})

# Max file size to index (skip minified/generated files).
_MAX_INDEX_FILE_SIZE = 102_400  # 100 KB

# Repo map output budget (characters).  ~1000 tokens.
_MAX_MAP_CHARS = 4000

# Tree-sitter node types that represent symbols, per language.
_SYMBOL_NODE_TYPES = {
    "python": {
        "function_definition": "def",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
    },
    "go": {
        "function_declaration": "func",
        "method_declaration": "func",
        "type_spec": "type",
    },
    "rust": {
        "function_item": "fn",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "impl",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
    },
    "java": {
        "class_declaration": "class",
        "method_declaration": "method",
        "interface_declaration": "interface",
    },
}


def is_indexable(path: str) -> bool:
    """Return True if the file extension is in the allowlist."""
    ext = os.path.splitext(path)[1].lower()
    return ext in _ALLOWED_EXTENSIONS


def _should_exclude(dir_name: str, exclude_dirs: frozenset) -> bool:
    """Check if a directory should be excluded from indexing."""
    return dir_name in exclude_dirs or dir_name.endswith(".egg-info")


def _get_declarator_name(node) -> Optional[str]:
    """Recursively extract name from C/C++ declarator chain."""
    if node.type in ("identifier", "type_identifier", "field_identifier"):
        return node.text.decode("utf-8")
    decl = node.child_by_field_name("declarator")
    if decl:
        return _get_declarator_name(decl)
    name = node.child_by_field_name("name")
    if name:
        return name.text.decode("utf-8")
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return child.text.decode("utf-8")
    return None


def _get_name(node) -> Optional[str]:
    """Extract the symbol name from a tree-sitter definition node."""
    # Named "name" field (Python, JS, Go, Java, etc.)
    name_node = node.child_by_field_name("name")
    if name_node and name_node.type in (
        "identifier", "type_identifier", "field_identifier", "property_identifier",
    ):
        return name_node.text.decode("utf-8")

    # "type" field (Rust impl blocks)
    type_node = node.child_by_field_name("type")
    if type_node and type_node.type == "type_identifier":
        return type_node.text.decode("utf-8")

    # Declarator chain (C/C++ function definitions)
    decl = node.child_by_field_name("declarator")
    if decl:
        return _get_declarator_name(decl)

    # Fallback: first identifier-like direct child
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "field_identifier"):
            return child.text.decode("utf-8")

    return None


def _walk_tree(node, node_types: dict, language: str) -> list:
    """Recursively walk the AST and extract symbols with nesting."""
    symbols = []

    if node.type in node_types:
        name = _get_name(node)
        if name:
            symbol = {
                "name": name,
                "kind": node_types[node.type],
                "line": node.start_point[0] + 1,
                "children": [],
            }
            # Recurse into children for nested definitions (e.g. methods in a class).
            child_types = _SYMBOL_NODE_TYPES.get(language, {})
            for child in node.children:
                symbol["children"].extend(_walk_tree(child, child_types, language))
            symbols.append(symbol)
            return symbols

    for child in node.children:
        symbols.extend(_walk_tree(child, node_types, language))

    return symbols


def extract_symbols(source: bytes, language: str) -> list:
    """Parse source bytes with tree-sitter and return symbol dicts.

    Each dict: {"name": str, "kind": str, "line": int, "children": list}
    Returns [] if tree-sitter is unavailable or language is unsupported.
    """
    if _get_parser is None or language not in _SYMBOL_NODE_TYPES:
        return []

    parser = _get_parser(language)
    tree = parser.parse(source)
    node_types = _SYMBOL_NODE_TYPES[language]
    return _walk_tree(tree.root_node, node_types, language)


def _format_symbols(rel_path: str, symbols: list, indent: int = 2) -> str:
    """Format extracted symbols into a compact text representation."""
    lines = [f"{rel_path}:"]
    for sym in symbols:
        prefix = " " * indent
        lines.append(f"{prefix}{sym['kind']} {sym['name']}")
        for child in sym.get("children", []):
            child_prefix = " " * (indent + 2)
            lines.append(f"{child_prefix}{child['kind']} {child['name']}")
    return "\n".join(lines)


def generate_repo_map(root_dir: str, exclude_dirs: Optional[set] = None) -> str:
    """Walk the project tree and generate a compact symbol map.

    Returns a multi-line string listing files and their top-level symbols.
    Skips files outside the allowlist, in excluded directories, or over 100 KB.
    """
    root = Path(root_dir).resolve()
    excl = _DEFAULT_EXCLUDE_DIRS | frozenset(exclude_dirs or set())

    file_entries = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place.
        dirnames[:] = sorted(d for d in dirnames if not _should_exclude(d, excl))

        for fname in sorted(filenames):
            full_path = os.path.join(dirpath, fname)
            if not is_indexable(full_path):
                continue

            # Guard against symlinks escaping the project root.
            try:
                resolved = Path(full_path).resolve()
            except OSError:
                continue
            if not resolved.is_relative_to(root):
                continue

            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue
            if size > _MAX_INDEX_FILE_SIZE:
                continue

            ext = os.path.splitext(fname)[1].lower()
            lang = _EXT_TO_LANG.get(ext)
            if not lang:
                continue

            try:
                with open(full_path, "rb") as f:
                    source = f.read()
            except OSError:
                continue

            symbols = extract_symbols(source, lang)
            if symbols:
                rel = os.path.relpath(full_path, root)
                file_entries.append(_format_symbols(rel, symbols))

    if not file_entries:
        return ""

    full_map = "\n\n".join(file_entries)
    if len(full_map) <= _MAX_MAP_CHARS:
        return full_map

    # Truncate to budget, keeping whole file entries.
    truncated = []
    char_count = 0
    for entry in file_entries:
        needed = len(entry) + (2 if truncated else 0)
        if char_count + needed > _MAX_MAP_CHARS:
            remaining = len(file_entries) - len(truncated)
            truncated.append(f"... ({remaining} more files)")
            break
        truncated.append(entry)
        char_count += needed

    return "\n\n".join(truncated)
