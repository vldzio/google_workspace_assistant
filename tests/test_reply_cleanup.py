from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_api.reply import clean_reply  # noqa: E402

GOOD = (
    "Mon Nov 16, 09:00-09:45 UTC - Weekly planning (Room Orion, with Maya)\n"
    "Tue Nov 17, 14:00-14:30 UTC - 1:1 with Maya Chen (Video call)"
)


def test_clean_reply_leaves_a_good_answer_and_its_markdown_untouched():
    assert clean_reply(GOOD) == GOOD
    md = "**Primary calendar:**\n- Mon Nov 16 - **Weekly planning**"
    assert clean_reply(md) == md  # the UI renders Markdown, the server must not strip it


def test_leading_narration_and_duplicate_answer_are_dropped():
    raw = (
        "The user wants to know what's on their calendar this week. Let me summarize the events.\n\n"
        "Primary calendar:\n- Mon Nov 16 - Weekly planning\n\n"
        "Here's your calendar for the week:\n\n**Primary calendar:**\n- Mon Nov 16 - Weekly planning"
    )
    out = clean_reply(raw)
    assert out.startswith("Here's your calendar for the week")
    assert "The user wants" not in out and out.count("Weekly planning") == 1 and "**Primary" in out


def test_narration_only_reply_is_not_emptied_and_think_blocks_go():
    assert clean_reply("Let me check that.") == "Let me check that."
    assert clean_reply("<think>hmm</think>You have 4 emails.") == "You have 4 emails."
    assert clean_reply("Here are your four most recent emails:\n\nA\nB").startswith("Here are your four")
