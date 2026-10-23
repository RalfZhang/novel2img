import pytest

from novel2img.tags import sanitize_prompt, sanitize_tag, split_tags


def test_split_tags():
    assert split_tags(" a, b ,, c ,") == ["a", "b", "c"]


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("1girl", ["1girl"]),
        ("Looking_At_Viewer", ["looking at viewer"]),
        ("from above", ["from above"]),  # short prepositional tags are fine
        ("  Blush. ", ["blush"]),
        ("half-closed eyes", ["half closed eyes"]),
        ("", []),
        # sentences squashed into one tag are split at connecting words
        ("her_body_type_is_petite_with_wide_hips", ["body type", "petite", "wide hips"]),
        (
            "standing between two huge stone pillars in the rain",
            ["standing", "two huge stone pillars", "rain"],
        ),
        ("the end", ["end"]),
        # pieces that stay longer than four words are dropped
        ("a very long description without any connecting words at all", []),
    ],
)
def test_sanitize_tag(tag, expected):
    assert sanitize_tag(tag) == expected


def test_sanitize_prompt_normalizes_and_deduplicates():
    prompt = "1girl, Blush, blush., looking_at_viewer, looking at viewer,,  "
    assert sanitize_prompt(prompt) == "1girl, blush, looking at viewer"
