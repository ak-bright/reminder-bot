import string

import pytest

from reminderbot.strings import DEFAULT_LANGUAGE, STRINGS, t


def test_every_language_has_every_key():
    english_keys = set(STRINGS[DEFAULT_LANGUAGE])
    for lang, table in STRINGS.items():
        assert set(table) == english_keys, f"language {lang!r} is missing keys"


@pytest.mark.parametrize("key", sorted(STRINGS[DEFAULT_LANGUAGE]))
def test_every_string_formats_with_its_placeholders(key):
    template = STRINGS[DEFAULT_LANGUAGE][key]
    names = {field for _, field, _, _ in string.Formatter().parse(template) if field}
    result = t(key, **{name: "X" for name in names})
    assert result.strip()


def test_unknown_language_falls_back_to_english():
    assert t("help.text", lang="xx") == t("help.text")


def test_placeholders_are_filled():
    assert "Ama" in t("start.welcome", name="Ama")
