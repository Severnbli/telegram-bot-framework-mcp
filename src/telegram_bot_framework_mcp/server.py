"""MCP server for MajMcCloud/TelegramBotFramework (NuGet: TelegramBotBase).

Reads a local git clone (baked into the Docker image at a pinned ref).
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import tarfile
from functools import lru_cache
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_DIR = Path(os.environ.get("TGBOTBASE_DIR", "/data/repo"))
NUGET_VERSION = os.environ.get("TGBOTBASE_NUGET_VERSION", "unknown")
MAX_CHARS = 40_000
SRC_PREFIXES = ("TelegramBotBase", "Examples")

mcp = FastMCP("telegram-bot-framework")


# ---------- helpers ----------
def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True, text=True)
    if r.returncode:
        raise ValueError(r.stderr.strip() or "git failed")
    return r.stdout


def _clip(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n\n... [truncated, {len(text) - MAX_CHARS} more chars]"


def _safe(path: str) -> Path | None:
    p = (REPO_DIR / path).resolve()
    return p if p.is_file() and REPO_DIR.resolve() in p.parents and ".git" not in p.parts else None


@lru_cache(maxsize=1)
def _files() -> tuple[str, ...]:
    return tuple(_git("ls-files").splitlines())


# ---------- C# symbol index ----------
TYPE_RE = re.compile(
    r"^\s*(?P<mods>(?:(?:public|internal|protected|private|abstract|static|sealed|partial|readonly|unsafe)\s+)*)"
    r"(?P<kind>class|interface|enum|struct|record)\s+(?P<name>\w+)(?P<gen><[^>{]*>)?\s*(?::\s*(?P<bases>[^\n{]+?))?\s*(?:where\b[^\n{]*)?$"
)
MEMBER_RE = re.compile(r"^\s*(public|protected)\s+(?!class\b|interface\b|enum\b|struct\b|record\b)([^=;{(]+?(?:\([^)]*\)|\s*\{|\s*=>|;|\s*$))")


def parse_cs(text: str) -> list[dict]:
    """Return types: {kind,name,bases,doc,members:[sig]} (regex based, good enough for API diffs)."""
    types, cur, doc = [], None, []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("///"):
            doc.append(re.sub(r"</?[a-zA-Z][^>]*>", "", s[3:]).strip())
            continue
        m = TYPE_RE.match(line)
        if m and not s.startswith(("//", "*")):
            cur = {"kind": m["kind"], "name": m["name"] + (m["gen"] or ""), "bases": (m["bases"] or "").strip(),
                   "public": "public" in m["mods"], "doc": " ".join(d for d in doc if d), "members": []}
            types.append(cur)
        elif cur and (mm := MEMBER_RE.match(line)):
            sig = re.sub(r"\s+", " ", mm.group(0)).strip(" {=>")
            cur["members"].append(sig)
        if s and not s.startswith("["):
            doc = []
    return types


@lru_cache(maxsize=1)
def _symbols() -> tuple[tuple[str, dict], ...]:
    out = []
    for p in _files():
        if p.endswith(".cs") and p.startswith(SRC_PREFIXES) and (f := _safe(p)):
            for t in parse_cs(f.read_text("utf-8", "replace")):
                out.append((p, t))
    return tuple(out)


def _symbols_at(ref: str) -> dict[str, dict]:
    """Public API of a git ref: {'Type': {'bases':..., 'members': set()}} for the main library only."""
    raw = subprocess.run(["git", "-C", str(REPO_DIR), "archive", ref, "TelegramBotBase"], capture_output=True)
    if raw.returncode:
        raise ValueError(raw.stderr.decode().strip())
    api: dict[str, dict] = {}
    with tarfile.open(fileobj=io.BytesIO(raw.stdout)) as tar:
        for m in tar:
            if m.isfile() and m.name.endswith(".cs") and "/obj/" not in m.name:
                for t in parse_cs(tar.extractfile(m).read().decode("utf-8", "replace")):
                    if t["public"]:
                        e = api.setdefault(t["name"], {"bases": t["bases"], "members": set(), "file": m.name})
                        e["members"].update(t["members"])
    return api


# ---------- tools ----------
@mcp.tool()
def framework_version() -> str:
    """Which framework version this server's source corresponds to (NuGet version, git commit, date)."""
    sha = _git("rev-parse", "HEAD").strip()
    date = _git("log", "-1", "--format=%cI").strip()
    csproj = _safe("TelegramBotBase/TelegramBotBase.csproj")
    deps = re.findall(r'PackageReference Include="([^"]+)" Version="([^"]+)"', csproj.read_text() if csproj else "")
    tfm = re.search(r"<TargetFrameworks>([^<]+)", csproj.read_text()) if csproj else None
    return (f"TelegramBotBase NuGet version: {NUGET_VERSION}\ncommit: {sha}\ncommit date: {date}\n"
            f"target frameworks: {tfm.group(1) if tfm else '?'}\n"
            "dependencies: " + ", ".join(f"{n} {v}" for n, v in deps))


@mcp.tool()
def get_changes(from_ref: str, to_ref: str = "HEAD", max_items: int = 60) -> str:
    """Public API diff of the TelegramBotBase library between two git refs (tags, branches, SHAs):
    added/removed types and added/removed public members, plus commit list. Only refs present in the clone work."""
    try:
        a, b = _symbols_at(from_ref), _symbols_at(to_ref)
        log = _git("log", "--oneline", "-n", "30", f"{from_ref}..{to_ref}").strip()
    except ValueError as e:
        return f"Error: {e}. Use list_refs to see available refs."
    out = [f"API diff {from_ref} -> {to_ref}"]
    out += [f"+ type {n}" for n in sorted(b.keys() - a.keys())]
    out += [f"- type {n}" for n in sorted(a.keys() - b.keys())]
    for n in sorted(a.keys() & b.keys()):
        if a[n]["bases"] != b[n]["bases"]:
            out.append(f"~ {n}: bases '{a[n]['bases']}' -> '{b[n]['bases']}'")
        out += [f"  + {n}: {m}" for m in sorted(b[n]["members"] - a[n]["members"])]
        out += [f"  - {n}: {m}" for m in sorted(a[n]["members"] - b[n]["members"])]
    if len(out) > max_items:
        out = out[:max_items] + [f"... {len(out) - max_items} more"]
    if len(out) == 1:
        out.append("(no public API changes detected)")
    return _clip("\n".join(out) + "\n\nCommits:\n" + (log or "(none)"))


@mcp.tool()
def list_refs() -> str:
    """List tags and branches available for get_changes."""
    return _git("for-each-ref", "--format=%(refname:short) %(objectname:short) %(creatordate:short)",
                "--sort=-creatordate", "refs/tags", "refs/remotes")


@mcp.tool()
def list_symbols(query: str = "", kind: str = "", max_results: int = 50) -> str:
    """List C# types (class/interface/enum/struct/record) by name substring and optional kind."""
    q, out = query.lower(), []
    for path, t in _symbols():
        if q in t["name"].lower() and (not kind or t["kind"] == kind):
            base = f" : {t['bases']}" if t["bases"] else ""
            out.append(f"{t['kind']} {t['name']}{base}  [{path}]")
    return "\n".join(out[:max_results]) or "No symbols."


@mcp.tool()
def get_symbol(name: str) -> str:
    """Show a type: doc comment, bases, public/protected members and file path. Use get_file for full source."""
    res = []
    for path, t in _symbols():
        if t["name"].split("<")[0] == name.split("<")[0]:
            res.append(f"{t['kind']} {t['name']}" + (f" : {t['bases']}" if t["bases"] else "")
                       + f"\nfile: {path}\ndoc: {t['doc'] or '-'}\nmembers:\n  " + "\n  ".join(t["members"]))
    return _clip("\n\n".join(res)) or f"No type named {name!r}."


@mcp.tool()
def find_subclasses(base: str) -> str:
    """Find types that inherit from / implement `base` (e.g. FormBase, ControlBase, IStateMachine)."""
    out = [f"{t['kind']} {t['name']} : {t['bases']}  [{p}]" for p, t in _symbols()
           if re.search(rf"\b{re.escape(base)}\b", t["bases"])]
    return "\n".join(out) or "None found."


@mcp.tool()
def list_files(prefix: str = "", extension: str = "") -> str:
    """List repository files filtered by path prefix and extension."""
    return _clip("\n".join(p for p in _files() if p.startswith(prefix) and p.endswith(extension))) or "No files."


@mcp.tool()
def get_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read a repository file (optionally a line range)."""
    f = _safe(path)
    if not f:
        return f"File not found: {path}. Use list_files."
    lines = f.read_text("utf-8", "replace").splitlines()
    sel = lines[max(start_line - 1, 0): end_line or None]
    return _clip("\n".join(f"{i}: {l}" for i, l in enumerate(sel, max(start_line, 1))))


@mcp.tool()
def search_code(query: str, extension: str = ".cs", path_prefix: str = "", regex: bool = False, max_results: int = 30) -> str:
    """Search the source (substring or regex) and return path:line: text."""
    pat = re.compile(query if regex else re.escape(query), re.I)
    out = []
    for p in _files():
        if p.endswith(extension) and p.startswith(path_prefix) and (f := _safe(p)):
            for n, line in enumerate(f.read_text("utf-8", "replace").splitlines(), 1):
                if pat.search(line):
                    out.append(f"{p}:{n}: {line.strip()}")
                    if len(out) >= max_results:
                        return "\n".join(out)
    return "\n".join(out) or "No matches."


def _sections() -> list[tuple[str, str]]:
    f = _safe("README.md")
    secs, fence, cur = [], False, None
    for line in (f.read_text("utf-8") if f else "").splitlines():
        if line.startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            cur = [m[1].strip(), [line]]
            secs.append(cur)
        elif cur:
            cur[1].append(line)
    return [(t, "\n".join(b)) for t, b in secs]


@mcp.tool()
def list_doc_sections() -> str:
    """List README sections."""
    return "\n".join(t for t, _ in _sections())


@mcp.tool()
def get_doc_section(title: str) -> str:
    """Get README section(s) by case-insensitive partial title, e.g. 'ButtonGrid'."""
    t = title.lower()
    m = [b for s, b in _sections() if s.lower() == t] or [b for s, b in _sections() if t in s.lower()]
    return _clip("\n\n".join(m[:3])) if m else f"No section {title!r}."


@mcp.tool()
def list_examples() -> str:
    """List C# example and test-bot files."""
    return _clip("\n".join(p for p in _files() if p.startswith(("Examples/", "TelegramBotBase.Test/")) and p.endswith(".cs")))


@mcp.resource("tgbotbase://readme")
def readme() -> str:
    """Full README."""
    f = _safe("README.md")
    return f.read_text("utf-8") if f else ""


def main() -> None:
    # stdio (default, for `docker run -i`) or streamable-http (for hosting; served at /mcp)
    mcp.run(transport=os.environ.get("TGBOTBASE_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
