"""Smoke tests, run inside the built image:
docker run --rm -v "$PWD/tests:/tests:ro" --entrypoint python IMAGE /tests/smoke.py
"""
import json
import subprocess
import sys

from telegram_bot_framework_mcp import server as s

EXPECTED_VERSION = sys.argv[1] if len(sys.argv) > 1 else None


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


v = s.framework_version()
check("commit:" in v and (EXPECTED_VERSION is None or EXPECTED_VERSION in v), f"framework_version -> {v.splitlines()[0]}")
check("FormBase" in s.list_symbols("FormBase"), "list_symbols finds FormBase")
check("class FormBase" in s.get_symbol("FormBase") or "FormBase" in s.get_symbol("FormBase"), "get_symbol FormBase")
check("FormBase" in s.find_subclasses("FormBase") or s.find_subclasses("FormBase") != "None found.", "find_subclasses(FormBase)")
check("Quick start" in s.list_doc_sections(), "README sections parsed")
check("BotBaseBuilder" in s.get_doc_section("Quick start"), "get_doc_section(Quick start)")
check(".cs:" in s.search_code("ButtonGrid", path_prefix="TelegramBotBase"), "search_code")
check(s.list_examples().strip() != "", "list_examples")
check(s.get_file("README.md", 1, 3).startswith("1:"), "get_file line range")
check(s.get_file("../etc/passwd").startswith("File not found"), "path traversal rejected")
check("Quick start" in s.list_guide_sections() or "Project setup" in s.list_guide_sections(), "list_guide_sections")
check("ConfirmAction" in s.get_gotchas("button spins forever"), "get_gotchas finds ConfirmAction")
check("Message loop" in s.get_guide_section("3.4") or "message loop" in s.get_guide_section("3.4").lower(), "get_guide_section 3.4")
check("RequestDispatcher" in s.search_guide("dispatcher"), "search_guide")
changes = s.get_changes("v7.1.0", "HEAD")
check(changes.startswith("API diff v7.1.0 -> HEAD"), "get_changes v7.1.0..HEAD")

# stdio handshake with the real entrypoint
p = subprocess.Popen(["telegram-bot-framework-mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def send(o): p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}}})
p.stdout.readline()
send({"jsonrpc": "2.0", "method": "notifications/initialized"})
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
tools = {t["name"] for t in json.loads(p.stdout.readline())["result"]["tools"]}
p.kill()
check({"framework_version", "get_changes", "get_symbol", "search_code", "get_guide_section", "get_gotchas", "ask"} <= tools, f"stdio tools/list ({len(tools)} tools)")
print("all smoke tests passed")
