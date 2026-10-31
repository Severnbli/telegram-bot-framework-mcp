"""Search-quality tests for the guide tools (no pinned source needed, only knowledge/SKILL.md):
TGBOTBASE_GUIDE=knowledge/SKILL.md python tests/test_search.py
Also run in CI inside the image (see smoke.py usage).
"""
import os
import sys

from telegram_bot_framework_mcp import server as s


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


def top(q: str, n: int = 3) -> str:
    return s.search_guide(q, n)


check(s._tokens("How do I handle a button click?") == ["handl", "button", "click"], "stop words dropped, stems made")
check("6." in top("how to handle button click inline keyboard"), "NL question finds button sections")
check("No matches" not in top("how do I send a message"), "NL question without exact phrase still matches")
check("7.2" in top("calendar date picker"), "calendar -> 7.2 controls")
check("CallbackDataTooLongException" in s.get_gotchas("CallbackDataTooLongException"), "gotcha by exception name")
check("ConfirmAction" in s.get_gotchas("button keeps spinning"), "gotcha by paraphrase")
check("RequestDispatcher" in top("dispatcher"), "single keyword still works")
check("thread" not in s._tokens("read") and "No matches" in top("zzzzqqqq"), "nonsense -> no matches")
check(s.search_guide("the of a").startswith("Give some keywords"), "only stop words -> hint")
check("Closest:" in s.get_guide_section("navigaton"), "guide section typo suggests titles")
check(len(top("button", 99).split("\n## ")) <= 15, "result count capped")
check(s.mcp.instructions and "ask" in s.mcp.instructions, "server instructions set")
print("all search tests passed")
