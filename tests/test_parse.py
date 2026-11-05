import pytest

import stages


def test_parse_bare_json():
    assert stages._parse('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    assert stages._parse('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_fence_without_language_tag():
    assert stages._parse('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_surrounded_by_prose():
    assert stages._parse('Sure! Here you go:\n{"a": {"b": 2}}\nHope that helps.') == {"a": {"b": 2}}


def test_parse_fence_after_prose():
    assert stages._parse('Here:\n```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize("bad", [None, "", "no json here", "[1, 2]", '{"a": '])
def test_parse_rejects_non_objects(bad):
    with pytest.raises(ValueError):
        stages._parse(bad)


def test_with_defaults_fills_missing_keys():
    rt = stages._with_defaults('{"answer": "hi"}', {"answer": "x", "in_sop": False})
    assert rt == {"answer": "hi", "in_sop": False}


def test_with_defaults_falls_back_on_garbage():
    df = {"answer": "x"}
    rt = stages._with_defaults("not json", df)
    assert rt == df and rt is not df
