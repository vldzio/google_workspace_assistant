"""Post-processing for model replies in the demo.

Free-tier models do not reliably obey "give only the final answer" in the system prompt, so the API
enforces it: drop <think> blocks, leading "Let me... / The user wants..." narration and the duplicate
answer some models emit after it. Formatting (Markdown) is left alone; the UI renders it.
Nothing here invents content; it only removes text.
"""
from __future__ import annotations

import re

_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
_NARRATION = re.compile(
    r"^(let me|let's|the user|i('ve| have| will| need| should| am going| can see| now)\b|i'll|now i|okay,|ok,|first,? i|"
    r"based on the (tool|results|data)|looking at the (tool|results))",
    re.I,
)
_HERE = re.compile(r"^here('s| is| are)\b", re.I)


def clean_reply(text: str) -> str:
    text = _THINK.sub("", text or "")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    while len(paras) > 1 and _NARRATION.match(paras[0]):
        paras.pop(0)
    # a model that narrated and then answered often answers twice: keep from the last "Here's ..." intro
    for i in range(len(paras) - 1, 0, -1):
        if _HERE.match(paras[i]):
            paras = paras[i:]
            break
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(paras)).strip()
