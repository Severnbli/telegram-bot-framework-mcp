"""MCP server for MajMcCloud/TelegramBotFramework (NuGet: TelegramBotBase).

Reads a local git clone (baked into the Docker image at a pinned ref).
"""
from __future__ import annotations

import difflib
import io
import math
import os
import re
import subprocess
import tarfile
from functools import lru_cache
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_DIR = Path(os.environ.get("TGBOTBASE_DIR", "/data/repo"))
GUIDE_PATH = Path(os.environ.get("TGBOTBASE_GUIDE", "/data/knowledge/SKILL.md"))
NUGET_VERSION = os.environ.get("TGBOTBASE_NUGET_VERSION", "unknown")
MAX_CHARS = 40_000
SRC_PREFIXES = ("TelegramBotBase", "Examples")

# host/port are passed explicitly: inside Docker the server must listen on 0.0.0.0 (the compose file
# publishes the port on the host's 127.0.0.1 only), and relying on FASTMCP_* env alone proved fragile.
INSTRUCTIONS = (
    "Knowledge server for building Telegram bots with the TelegramBotBase .NET framework. "
    "For any how-to question call `ask` first (one call: ranked guide sections, known pitfalls, matching types). "
    "Then read a full section with `get_guide_section`, check exact signatures with `get_symbol`, and look at real "
    "code with `search_code` / `get_file` / `list_examples`. For an error or odd behaviour use `get_gotchas`. "
    "Prefer the guide over guessing: the framework has its own conventions (forms, controls, message.ConfirmAction())."
)

mcp = FastMCP(
    "telegram-bot-framework",
    instructions=INSTRUCTIONS,
    host=os.environ.get("FASTMCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("FASTMCP_PORT", "8000")),
)


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
    if not res:
        names = sorted({t["name"].split("<")[0] for _, t in _symbols()})
        close = difflib.get_close_matches(name.split("<")[0], names, n=5, cutoff=0.6)
        return f"No type named {name!r}." + (f" Did you mean: {', '.join(close)}?" if close else " Try list_symbols or ask.")
    hints = _guide_hints(name.split("<")[0])
    return _clip("\n\n".join(res)) + (f"\n\nGuide mentions it in: {'; '.join(hints)} (use get_guide_section)" if hints else "")


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
def search_code(query: str, extension: str = ".cs", path_prefix: str = "", max_results: int = 30) -> str:
    """Case-insensitive substring search of the source; returns path:line: text."""
    if not query or len(query) > 200:
        return "Query must be 1-200 characters."
    q = query.lower()
    max_results = min(max_results, 100)
    out = []
    for p in _files():
        if p.endswith(extension) and p.startswith(path_prefix) and (f := _safe(p)):
            for n, line in enumerate(f.read_text("utf-8", "replace").splitlines(), 1):
                if q in line.lower():
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


# ---------- curated guide (knowledge/SKILL.md) ----------
@lru_cache(maxsize=1)
def _guide_sections() -> tuple[tuple[str, str], ...]:
    """Split the guide into (heading, body) at ## and ### headings, ignoring fenced code."""
    if not GUIDE_PATH.is_file():
        return ()
    secs, fence, cur = [], False, None
    for line in GUIDE_PATH.read_text("utf-8").splitlines():
        if line.startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^#{2,3}\s+(.*)", line)
        if m:
            cur = [m[1].strip(), [line]]
            secs.append(cur)
        elif cur:
            cur[1].append(line)
    return tuple((t, "\n".join(b)) for t, b in secs)


def _guide_hints(name: str) -> list[str]:
    return [t for t, b in _guide_sections() if re.search(rf"\b{re.escape(name)}\b", b)][:5]


@mcp.tool()
def list_guide_sections() -> str:
    """List sections of the curated how-to guide (decision tables, patterns, gotchas, checklist)."""
    return "\n".join(t for t, _ in _guide_sections()) or "No guide installed."


@mcp.tool()
def get_guide_section(query: str) -> str:
    """Read guide section(s) by number or partial title, e.g. '3.4', 'Navigation', 'Checklist'."""
    q = query.lower().strip()
    m = [b for t, b in _guide_sections() if t.lower().startswith(q.rstrip(".") + ".") or t.lower() == q]
    m = m or [b for t, b in _guide_sections() if q in t.lower()]
    if m:
        return _clip("\n\n".join(m[:3]))
    close = difflib.get_close_matches(query, [t for t, _ in _guide_sections()], n=3, cutoff=0.4)
    return f"No guide section {query!r}." + (f" Closest: {'; '.join(close)}." if close else "") + " Use search_guide or list_guide_sections."


# ---------- natural-language search ----------
_STOP = frozenset(
    "a an the to of in on for and or is are was be been can could do does did how i me my we you your it its with what "
    "when where why which who should would will from into this that these those as at by use using get make want need "
    "please about there not no yes if then than so just some any all tell show give explain way best "
    "to".split()
)


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return w[:-1] if len(w) > 4 and w.endswith("e") else w


def _tokens(text: str) -> list[str]:
    """Query words -> distinct stems, without filler words ('how do I ...')."""
    out: list[str] = []
    for w in re.findall(r"[A-Za-z0-9_]+", text):
        lw = w.lower()
        if lw in _STOP or len(lw) < 2:
            continue
        st = _stem(lw)
        if st not in out:
            out.append(st)
    return out


def _rank(sections: tuple[tuple[str, str], ...] | list[tuple[str, str]], toks: list[str], limit: int):
    """Rank (title, body) sections for the stems `toks`. Rarer words weigh more; matching more distinct words
    beats repeating one word. Returns [(score, title, body)] best first."""
    if not toks or not sections:
        return []
    pats = {k: re.compile(r"\b" + re.escape(k), re.I) for k in toks}  # word-start: 'read' must not hit 'thread'
    n = len(sections)
    df = {k: sum(1 for t, b in sections if pats[k].search(t) or pats[k].search(b)) for k in toks}
    scored = []
    for t, b in sections:
        hit = [k for k in toks if pats[k].search(t) or pats[k].search(b)]
        if not hit:
            continue
        sc = 0.0
        for k in hit:
            idf = math.log(1 + n / df[k])
            sc += idf * ((3 if pats[k].search(t) else 0) + min(len(pats[k].findall(b)), 5) ** 0.5)
        scored.append((sc * len(hit) ** 1.5, t, b))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def _snippets(body: str, toks: list[str], n: int = 3, width: int = 220) -> list[str]:
    """The n lines of a section that match the most distinct query words (headings and table rules skipped)."""
    best = []
    for i, line in enumerate(body.splitlines()):
        st = line.strip()
        if not st or st.startswith("#") or re.match(r"^\|[-| ]+\|$", st) or st.startswith("```"):
            continue
        lw = st.lower()
        c = sum(1 for k in toks if re.search(r"\b" + re.escape(k), lw))
        if c:
            best.append((-c, i, st))
    best.sort()
    return [x[2][:width] + ("..." if len(x[2]) > width else "") for x in sorted(best[:n], key=lambda x: x[1])]


def _gotcha_rows() -> list[tuple[str, str]]:
    rows = []
    for t, b in _guide_sections():
        if "gotchas" in t.lower():
            for line in b.splitlines():
                if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
                    cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
                    if len(cells) >= 2 and cells[0].lower() != "symptom":
                        rows.append((cells[0], cells[1]))
    return rows


@mcp.tool()
def search_guide(query: str, max_results: int = 5) -> str:
    """Search the how-to guide with a plain-English question or keywords (e.g. 'handle a button click', 'dispatcher').
    Returns the best-matching sections, most relevant first, each with the key matching lines.
    Read a whole section with get_guide_section."""
    toks = _tokens(query)
    if not toks:
        return "Give some keywords, e.g. 'inline keyboard' or 'navigate between forms'."
    ranked = _rank(_guide_sections(), toks, max(1, min(max_results, 15)))
    if not ranked:
        return f"No matches for {query!r}. Try fewer or different words, or list_guide_sections."
    out = []
    for _, t, b in ranked:
        out.append(f"## {t}  (get_guide_section {t.split()[0].rstrip('.')!r})")
        out += [f"   {x}" for x in _snippets(b, toks)]
    return "\n".join(out)


@mcp.tool()
def get_gotchas(symptom: str = "") -> str:
    """Known pitfalls as 'symptom -> cause & fix'. Pass words of your problem or error (e.g. 'spins forever',
    'CallbackDataTooLongException'), or nothing for all."""
    rows = _gotcha_rows()
    toks = _tokens(symptom)
    if toks:
        ranked = _rank([(a, a + " " + c) for a, c in rows], toks, 5)
        by_sym = dict(rows)
        rows = [(t, by_sym[t]) for _, t, _ in ranked]
    return "\n\n".join(f"Symptom: {a}\nCause/fix: {c}" for a, c in rows) or "No matching gotcha."


@mcp.tool()
def ask(question: str) -> str:
    """Best first call for any how-to question about building a bot with TelegramBotBase. Searches the guide, the
    known pitfalls, the type index and the README at once, and tells you which tool to call next."""
    toks = _tokens(question)
    if not toks:
        return "Ask a question, e.g. 'how do I show a calendar and read the chosen date?'"
    out = []
    secs = _rank(_guide_sections(), toks, 3)
    if secs:
        out.append("GUIDE SECTIONS (read with get_guide_section):")
        for _, t, b in secs:
            out.append(f"- {t}")
            out += [f"    {x}" for x in _snippets(b, toks, 2)]
    rows = _gotcha_rows()
    gr = _rank([(a, a + " " + c) for a, c in rows], toks, 2)
    if gr:
        by_sym = dict(rows)
        out.append("\nPOSSIBLY RELATED PITFALLS:")
        out += [f"- {t} -> {by_sym[t]}" for _, t, _ in gr]
    types: dict[str, tuple[int, str]] = {}
    for path, t in _symbols():
        words = [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+", t["name"].split("<")[0])]
        hit = sum(1 for k in toks if len(k) >= 4 and any(w.startswith(k) for w in words))
        if hit:
            types.setdefault(t["name"], (hit, f"{t['kind']} {t['name']}  [{path}]"))
    if types:
        best = sorted(types.values(), key=lambda x: (-x[0], len(x[1])))[:6]
        out.append("\nTYPES (details with get_symbol):")
        out += [f"- {d}" for _, d in best]
    rd = _rank(_sections(), toks, 2)
    if rd:
        out.append("\nREADME SECTIONS (get_doc_section): " + "; ".join(t for _, t, _ in rd))
    if not out:
        return f"Nothing found for {question!r}. Try other words, list_guide_sections or search_code."
    out.append("\nNEXT: get_guide_section for the full pattern, get_symbol for exact members, "
               "search_code / list_examples for real usage.")
    return _clip("\n".join(out))


@mcp.resource("tgbotbase://guide")
def guide_resource() -> str:
    """Curated how-to guide."""
    return GUIDE_PATH.read_text("utf-8") if GUIDE_PATH.is_file() else ""


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
