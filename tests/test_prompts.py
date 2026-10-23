from novel2img import prompts


def test_builtin_templates_exist():
    for name in prompts.NAMES:
        assert prompts.load_template(name).strip()


def test_render_fills_placeholders():
    text = prompts.render("scene_user", title="Chapter 1", body="It was raining.", max_scenes=3)
    assert "Chapter 1" in text
    assert "It was raining." in text
    assert "at most 3 scenes" in text
    assert "$" not in text


def test_render_leaves_dollar_signs_in_values_alone():
    text = prompts.render("scene_user", title="T", body="It cost $5, or ${price}.", max_scenes=1)
    assert "It cost $5, or ${price}." in text


def test_override_dir_replaces_only_the_templates_it_contains(tmp_path):
    (tmp_path / "scene_user.md").write_text("Custom: $title", encoding="utf-8")
    assert prompts.render("scene_user", tmp_path, title="X") == "Custom: X"
    assert prompts.render("adjust_user", tmp_path, input="{}").startswith("Input:")
