"""
Repo Ingestion Agent
====================
Clones any GitHub repo and parses its structure into structured data.
Supports Python, Jupyter notebooks, JS/TS, Java, Go, Rust, C++,
SQL, R, shell scripts, web files, config files, and more.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from core.config import settings

LANGUAGE_EXTENSIONS = {
    # Python
    ".py":    "python",
    ".pyw":   "python",
    ".pyx":   "python",
    # Jupyter notebooks
    ".ipynb": "jupyter",
    # JavaScript / TypeScript
    ".js":    "javascript",
    ".jsx":   "javascript",
    ".mjs":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "typescript",
    # JVM
    ".java":  "java",
    ".kt":    "kotlin",
    ".scala": "scala",
    # Systems
    ".go":    "go",
    ".rs":    "rust",
    ".cpp":   "cpp",
    ".cc":    "cpp",
    ".cxx":   "cpp",
    ".c":     "c",
    ".h":     "c",
    ".hpp":   "cpp",
    ".cs":    "csharp",
    # Scripting
    ".rb":    "ruby",
    ".php":   "php",
    ".sh":    "shell",
    ".bash":  "shell",
    ".ps1":   "powershell",
    # Data science
    ".r":     "r",
    ".R":     "r",
    ".sql":   "sql",
    # Web
    ".html":  "html",
    ".htm":   "html",
    ".css":   "css",
    ".scss":  "css",
    # Config / Data
    ".json":  "json",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".toml":  "toml",
    ".xml":   "xml",
    ".csv":   "csv",
    # Docs
    ".md":    "markdown",
    ".rst":   "markdown",
    ".txt":   "text",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage", ".pytest_cache",
    ".ipynb_checkpoints", "__MACOSX",
}

# Extensions we index but don't try to parse for functions/classes
TEXT_ONLY_LANGS = {
    "json", "yaml", "toml", "xml", "csv",
    "markdown", "text", "html", "css", "sql",
    "shell", "powershell", "r",
}


class RepoIngestionAgent:
    """Clone a GitHub repo and parse its structure into structured data."""

    def __init__(self):
        os.makedirs(settings.REPOS_DIR, exist_ok=True)

    # ── Public ──────────────────────────────────────────────────────────

    def ingest(self, repo_url: str, branch: str = "main") -> dict[str, Any]:
        repo_id   = hashlib.md5(repo_url.encode()).hexdigest()[:12]
        repo_path = Path(settings.REPOS_DIR) / repo_id

        if repo_path.exists():
            import stat
            def force_remove(func, path, exc):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
            shutil.rmtree(repo_path, onerror=force_remove)

        self._clone(repo_url, repo_path, branch)
        parsed = self._parse_repo(repo_path)

        parsed["repo_id"]   = repo_id
        parsed["repo_url"]  = repo_url
        parsed["repo_path"] = str(repo_path)
        return parsed

    # ── Clone ────────────────────────────────────────────────────────────

    def _clone(self, url: str, path: Path, branch: str):
        # Always delete first — handles stale dirs from previous failed clones
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            # Windows sometimes needs a moment to release file handles
            import time
            time.sleep(0.5)
        path.mkdir(parents=True, exist_ok=True)

        # Try gitpython first
        try:
            import git
            git.Repo.clone_from(url, path, depth=1)
            print(f"[Ingestion] gitpython clone succeeded")
            return
        except Exception as e:
            print(f"[Ingestion] gitpython failed: {e}")

        # Fallback: subprocess git
        try:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
                import time
                time.sleep(0.5)
            path.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--depth=1", url, str(path)],
                capture_output=True, text=True, timeout=180,
            )
            print(f"[Ingestion] git clone returncode: {result.returncode}")
            print(f"[Ingestion] git clone stdout: {result.stdout[:200]}")
            print(f"[Ingestion] git clone stderr: {result.stderr[:300]}")
            if result.returncode == 0:
                return
        except Exception as e:
            print(f"[Ingestion] subprocess clone failed: {e}")

        # Last resort stub
        print(f"[Ingestion] WARNING: all clone methods failed, creating stub")
        (path / "README.md").write_text(f"# Repo stub\nURL: {url}")
    # ── Parse repo ───────────────────────────────────────────────────────

    def _parse_repo(self, repo_path: Path) -> dict[str, Any]:
        files:     list[dict] = []
        functions: list[dict] = []
        classes:   list[dict] = []
        imports:   list[dict] = []
        lang_counts: dict[str, int] = {}

        # Debug — print everything found in the repo
        all_files = list(repo_path.rglob("*"))
        print(f"[Ingestion] total items in repo: {len(all_files)}")
        for fp in all_files[:30]:
            print(f"[Ingestion]   {fp.relative_to(repo_path)} | is_file={fp.is_file()} | suffix={fp.suffix}")

        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(s in file_path.parts for s in SKIP_DIRS):
                print(f"[Ingestion] SKIPPED (dir): {file_path.name}")
                continue
            # Skip very large files (>500KB)
            try:
                if file_path.stat().st_size > 500_000:
                    print(f"[Ingestion] SKIPPED (too large): {file_path.name}")
                    continue
            except Exception:
                continue

            ext  = file_path.suffix.lower()
            lang = LANGUAGE_EXTENSIONS.get(ext)
            if not lang:
                print(f"[Ingestion] SKIPPED (unknown ext): {file_path.name} | ext={ext}")
                continue

            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            rel = str(file_path.relative_to(repo_path)).replace("\\", "/")

            try:
                source = file_path.read_text(errors="ignore")
            except Exception:
                source = ""

            loc = source.count("\n") + 1
            fid = f"file:{rel}"

            # Parse functions/classes based on language
            if lang == "python":
                fns, cls, imps = self._parse_python(source, rel)
            elif lang == "jupyter":
                fns, cls, imps = self._parse_jupyter(source, rel)
            elif lang in TEXT_ONLY_LANGS:
                fns, cls, imps = [], [], []
            else:
                fns, cls, imps = self._parse_generic(source, rel, lang)

            file_info = {
                "id":        fid,
                "path":      rel,
                "language":  lang,
                "size":      file_path.stat().st_size,
                "loc":       loc,
                "functions": [{"name": f["name"]} for f in fns],
                "classes":   [{"name": c["name"]} for c in cls],
                # Store a short preview for RAG context
                "preview":   source[:300].strip(),
            }

            files.append(file_info)
            functions.extend(fns)
            classes.extend(cls)
            imports.extend(imps)

        # Pick primary language — prefer code over config
        CODE_PRIORITY = [
            "python","jupyter","javascript","typescript","java",
            "go","rust","cpp","c","csharp","kotlin","scala",
            "ruby","php","r","sql","shell",
        ]
        primary = "unknown"
        for lang in CODE_PRIORITY:
            if lang in lang_counts:
                primary = lang
                break
        if primary == "unknown" and lang_counts:
            primary = max(lang_counts, key=lang_counts.get)

        print(f"[Ingestion] parsed {len(files)} files, "
              f"{len(functions)} functions, {len(classes)} classes — "
              f"primary lang: {primary}")
        print(f"[Ingestion] language breakdown: {lang_counts}")

        return {
            "files":           files,
            "functions":       functions,
            "classes":         classes,
            "imports":         imports,
            "language":        primary,
            "language_counts": lang_counts,
            "stats": {
                "file_count":     len(files),
                "function_count": len(functions),
                "class_count":    len(classes),
            },
        }

    # ── Python AST parser ─────────────────────────────────────────────────

    def _parse_python(self, source: str, file_path: str):
        functions, classes, imports = [], [], []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return functions, classes, imports

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls = []
                for n in ast.walk(node):
                    if isinstance(n, ast.Call):
                        if isinstance(n.func, ast.Name):
                            calls.append(n.func.id)
                        elif isinstance(n.func, ast.Attribute):
                            calls.append(n.func.attr)

                complexity = 1 + sum(
                    1 for n in ast.walk(node)
                    if isinstance(n, (ast.If, ast.For, ast.While,
                                      ast.ExceptHandler, ast.With,
                                      ast.Assert, ast.comprehension))
                )
                functions.append({
                    "id":         f"func:{file_path}:{node.name}",
                    "name":       node.name,
                    "file":       file_path,
                    "line":       node.lineno,
                    "calls":      [c for c in calls if c],
                    "complexity": complexity,
                    "docstring":  ast.get_docstring(node) or "",
                })

            elif isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in ast.walk(node)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes.append({
                    "id":        f"class:{file_path}:{node.name}",
                    "name":      node.name,
                    "file":      file_path,
                    "line":      node.lineno,
                    "methods":   methods,
                    "docstring": ast.get_docstring(node) or "",
                })

            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append({
                    "from_file": file_path,
                    "module":    node.module,
                    "names":     [a.name for a in node.names],
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "from_file": file_path,
                        "module":    alias.name,
                        "names":     [],
                    })

        return functions, classes, imports

    # ── Jupyter notebook parser ───────────────────────────────────────────

    def _parse_jupyter(self, source: str, file_path: str):
        """
        Extract Python code cells from a .ipynb file and parse them.
        Also extracts markdown cells as text context.
        """
        functions, classes, imports = [], [], []
        try:
            nb = json.loads(source)
        except json.JSONDecodeError:
            return functions, classes, imports

        cells = nb.get("cells", [])
        combined_code = []

        for cell in cells:
            cell_type = cell.get("cell_type", "")
            src = "".join(cell.get("source", []))

            if cell_type == "code" and src.strip():
                combined_code.append(src)
            # markdown cells are captured via file preview

        # Parse all code cells as one combined Python source
        full_code = "\n\n".join(combined_code)
        if full_code.strip():
            fns, cls, imps = self._parse_python(full_code, file_path)
            functions.extend(fns)
            classes.extend(cls)
            imports.extend(imps)

        # Also extract top-level imports as structured data
        for cell in cells:
            if cell.get("cell_type") == "code":
                src = "".join(cell.get("source", []))
                for line in src.split("\n"):
                    line = line.strip()
                    if line.startswith("import ") or line.startswith("from "):
                        mod = line.split()[1].split(".")[0]
                        imports.append({
                            "from_file": file_path,
                            "module":    mod,
                            "names":     [],
                        })

        return functions, classes, imports

    # ── Generic regex parser ──────────────────────────────────────────────

    def _parse_generic(self, source: str, file_path: str, lang: str):
        functions, classes, imports = [], [], []

        patterns: dict[str, dict] = {
            "javascript": {
                "fn":  r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\s*(?:\([^)]*\)|\w+)\s*=>)",
                "cls": r"class\s+(\w+)",
                "imp": r'(?:import\s+.*?from\s+["\']([^"\']+)["\']|require\s*\(\s*["\']([^"\']+)["\']\s*\))',
            },
            "typescript": {
                "fn":  r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\s*(?:\([^)]*\)|\w+)\s*=>)",
                "cls": r"class\s+(\w+)",
                "imp": r'(?:import\s+.*?from\s+["\']([^"\']+)["\']|require\s*\(\s*["\']([^"\']+)["\']\s*\))',
            },
            "java": {
                "fn":  r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(",
                "cls": r"(?:public\s+)?(?:abstract\s+)?class\s+(\w+)",
                "imp": r"import\s+([\w.]+);",
            },
            "kotlin": {
                "fn":  r"fun\s+(\w+)\s*[(<]",
                "cls": r"(?:class|object|interface)\s+(\w+)",
                "imp": r"import\s+([\w.]+)",
            },
            "go": {
                "fn":  r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*[(<]",
                "cls": r"type\s+(\w+)\s+struct",
                "imp": r'"([\w./]+)"',
            },
            "rust": {
                "fn":  r"fn\s+(\w+)\s*[<(]",
                "cls": r"(?:struct|enum|impl)\s+(\w+)",
                "imp": r"use\s+([\w:]+)",
            },
            "cpp": {
                "fn":  r"(?:void|int|float|double|bool|char|auto|string)\s+(\w+)\s*\([^)]{0,100}\)\s*(?:const\s*)?[{;]",
                "cls": r"(?:class|struct)\s+(\w+)",
                "imp": r'#include\s+[<"]([^>"]+)[>"]',
            },
            "c": {
                "fn":  r"(?:void|int|float|double|char|long|short|unsigned)\s+(\w+)\s*\([^)]{0,100}\)\s*[{;]",
                "cls": r"struct\s+(\w+)",
                "imp": r'#include\s+[<"]([^>"]+)[>"]',
            },
            "c": {
                "fn":  r"(?:void|int|float|double|char|long|short|unsigned)\s+(\w+)\s*\([^)]{0,100}\)\s*[{;]",
                "cls": r"struct\s+(\w+)",
                "imp": r'#include\s+[<"]([^>"]+)[>"]',
            },
            "c": {
                "fn":  r"(?:void|int|float|double|char|long|short|unsigned)\s+(\w+)\s*\([^)]{0,100}\)\s*[{;]",
                "cls": r"struct\s+(\w+)",
                "imp": r'#include\s+[<"]([^>"]+)[>"]',
            },
            "c": {
                "fn":  r"(?:void|int|float|double|char|long|short|unsigned)\s+(\w+)\s*\([^)]{0,100}\)\s*[{;]",
                "cls": r"struct\s+(\w+)",
                "imp": r'#include\s+[<"]([^>"]+)[>"]',
            },
            "c": {
                "fn":  r"(?:void|int|float|double|bool|char)\s+(\w+)\s*\([^)]{0,100}\)\s*[{;]",
                "cls": r"struct\s+(\w+)",
                "imp": r'#include\s+[<"]([^>"]+)[>"]',
            },
            "csharp": {
                "fn":  r"(?:public|private|protected|static|virtual|override|\s)+[\w<>\[\]]+\s+(\w+)\s*\(",
                "cls": r"(?:public\s+)?(?:abstract\s+)?class\s+(\w+)",
                "imp": r"using\s+([\w.]+);",
            },
            "ruby": {
                "fn":  r"def\s+(\w+)",
                "cls": r"class\s+(\w+)",
                "imp": r"require\s+['\"]([^'\"]+)['\"]",
            },
            "php": {
                "fn":  r"function\s+(\w+)\s*\(",
                "cls": r"class\s+(\w+)",
                "imp": r"(?:require|include)(?:_once)?\s+['\"]([^'\"]+)['\"]",
            },
            "scala": {
                "fn":  r"def\s+(\w+)\s*[(<]",
                "cls": r"(?:class|object|trait)\s+(\w+)",
                "imp": r"import\s+([\w.]+)",
            },
        }

        p = patterns.get(lang, {})

        if "fn" in p:
            for m in re.finditer(p["fn"], source):
                name = next((g for g in m.groups() if g), None)
                if name:
                    functions.append({
                        "id":         f"func:{file_path}:{name}",
                        "name":       name,
                        "file":       file_path,
                        "line":       source[:m.start()].count("\n") + 1,
                        "calls":      [],
                        "complexity": 1,
                        "docstring":  "",
                    })

        if "cls" in p:
            for m in re.finditer(p["cls"], source):
                classes.append({
                    "id":        f"class:{file_path}:{m.group(1)}",
                    "name":      m.group(1),
                    "file":      file_path,
                    "line":      source[:m.start()].count("\n") + 1,
                    "methods":   [],
                    "docstring": "",
                })

        if "imp" in p:
            for m in re.finditer(p["imp"], source):
                # group(1) or group(2) — handles patterns with two capture groups (e.g. import + require)
                module = next((g for g in m.groups() if g), None)
                if not module:
                    continue
                imports.append({
                    "from_file": file_path,
                    "module":    module,
                    "names":     [],
                })

        return functions, classes, imports
