from novel2img.chapters import Chapter, split_chapters


def test_empty_text_has_no_chapters():
    assert split_chapters("") == []
    assert split_chapters(" \n\n\t") == []


def test_text_without_headings_is_one_untitled_chapter():
    assert split_chapters("  It was raining.\nShe ran.  ") == [
        Chapter(title="", body="It was raining.\nShe ran.")
    ]


def test_chinese_headings():
    text = (
        "第一章 风雪夜归\n雪下了一夜。\n\n\n"
        "第二章：山门\n他推开了门。\n\n"
        "　　第十二回 对决\n剑光一闪。\n"
        "第3章\n短。"
    )
    assert split_chapters(text) == [
        Chapter("第一章 风雪夜归", "雪下了一夜。"),
        Chapter("第二章：山门", "他推开了门。"),
        Chapter("第十二回 对决", "剑光一闪。"),
        Chapter("第3章", "短。"),
    ]


def test_sentences_that_start_like_headings_stay_in_the_body():
    text = "第一章 开端\n第二回合开始了。\n第三节课上，他睡着了。\n第一回，他输了。"
    assert split_chapters(text) == [
        Chapter("第一章 开端", "第二回合开始了。\n第三节课上，他睡着了。\n第一回，他输了。")
    ]


def test_english_headings():
    text = (
        "Chapter 1: The Storm\nRain.\n\n"
        "CHAPTER II\nWind.\n\n"
        "Chapter Twenty-One. Calm\nSun.\n\n"
        "## Chapter 4\nMarkdown.\n\n"
        "Chapters are fun, she said.\n"
    )
    assert split_chapters(text) == [
        Chapter("Chapter 1: The Storm", "Rain."),
        Chapter("CHAPTER II", "Wind."),
        Chapter("Chapter Twenty-One. Calm", "Sun."),
        Chapter("Chapter 4", "Markdown.\n\nChapters are fun, she said."),
    ]


def test_prologue_epilogue_and_their_chinese_equivalents():
    text = (
        "Prologue\nBefore.\nChapter 1\nDuring.\nEpilogue: Later\nAfter.\n"
        "楔子\n开始前。\n尾声\n结束后。"
    )
    assert [c.title for c in split_chapters(text)] == [
        "Prologue",
        "Chapter 1",
        "Epilogue: Later",
        "楔子",
        "尾声",
    ]


def test_text_before_the_first_heading_is_ignored():
    text = "The Lantern Keeper\nby Someone\n\nChapter 1\nBody."
    assert split_chapters(text) == [Chapter("Chapter 1", "Body.")]


def test_headings_without_a_body_are_skipped():
    text = "第一卷 风起\n第一章 初见\n正文。"
    assert split_chapters(text) == [Chapter("第一章 初见", "正文。")]


def test_long_lines_are_not_headings():
    text = "Chapter 1\nBody.\nChapter 2 " + "and so on " * 10 + "\nMore."
    assert len(split_chapters(text)) == 1


def test_windows_line_endings():
    assert split_chapters("Chapter 1\r\nA.\r\nChapter 2\r\nB.") == [
        Chapter("Chapter 1", "A."),
        Chapter("Chapter 2", "B."),
    ]
