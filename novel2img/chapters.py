"""Split a novel into chapters at their headings."""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Chapter", "split_chapters"]


@dataclass(frozen=True)
class Chapter:
    title: str  # empty when the text has no recognizable headings
    body: str


# Chinese: 第一章 / 第12回 / 第三卷 … plus 序章, 楔子, 尾声 … A separator or the end of the line
# must follow, so sentences such as "第二回合开始了" or "第一回，他输了" stay in the body.
_ZH_SEP = r"(?=$|[\s:：.．、·\-—–()（）\[\]【】《》「」『』\"“”'‘’])"
_ZH_HEADING = (
    r"第[ \t　]*[0-9０-９零〇一二三四五六七八九十百千万两]+[ \t　]*[章回节卷篇部集]"
    + _ZH_SEP
    + r"|(?:序章|序幕|楔子|引子|尾声|终章|后记)"
    + _ZH_SEP
)

# English: Chapter 1 / CHAPTER IV / Chapter Twenty-One, plus Prologue and Epilogue.
_EN_UNITS = "one|two|three|four|five|six|seven|eight|nine"
_EN_NUMBER = (
    rf"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:{_EN_UNITS}))?"
    r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    rf"|{_EN_UNITS}|hundred"
)
_EN_HEADING = rf"chapter[ \t]+(?:\d+|[ivxlcdm]+|{_EN_NUMBER})(?!\w)|(?:prologue|epilogue)(?!\w)"

# A heading is a whole line, optionally indented or marked up as a Markdown heading.
_HEADING_RE = re.compile(
    rf"^[ \t　]*(?:#{{1,6}}[ \t]*)?(?P<title>(?:{_ZH_HEADING}|{_EN_HEADING})[^\n]*?)[ \t　]*$",
    re.MULTILINE | re.IGNORECASE,
)
_MAX_HEADING_LENGTH = 80  # longer lines are prose that merely starts like a heading


def split_chapters(text: str) -> list[Chapter]:
    """Split ``text`` into chapters at headings such as "第一章 风雪夜归" or "Chapter 1: The Storm".

    Text before the first heading (book title, author, …) is ignored, and headings without a
    body (e.g. a volume heading right before a chapter heading) are skipped. Text without any
    heading is returned as a single untitled chapter.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    headings = [
        m for m in _HEADING_RE.finditer(text) if len(m.group("title")) <= _MAX_HEADING_LENGTH
    ]
    chapters = []
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[heading.end() : end].strip()
        if body:
            chapters.append(Chapter(title=heading.group("title"), body=body))
    return chapters or [Chapter(title="", body=text)]
