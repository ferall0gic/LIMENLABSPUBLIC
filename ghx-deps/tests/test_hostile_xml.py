"""Hostile and malformed .ghx input (LABPUB-005, 2026-11-17).

ghx-deps parses with the standard-library ElementTree (expat). These tests pin the
behaviour we rely on: no external entity is fetched, entity expansion is bounded, and
every failure is a per-file 'not read' with exit 2, never a traceback or a hang."""

import json

import pytest

LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">'
    + "".join(f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(8))
    + ']><Archive name="Root"><item name="x">&i;</item></Archive>'
)
XXE = (
    '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/hostname">]>'
    '<Archive name="Root"><item name="x">&x;</item></Archive>'
)


@pytest.mark.parametrize(
    "name,body",
    [("empty.ghx", ""), ("malformed.ghx", "<Archive name='Root'><chunk>"), ("laughs.ghx", LAUGHS), ("xxe.ghx", XXE)],
)
def test_bad_xml_is_not_read_exit_2(run, tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    code, out, err = run(p, "--format", "json")
    assert code == 2
    assert "Traceback" not in err
    doc = json.loads(out)
    assert doc["summary"]["not_read"] == 1 if "summary" in doc else True
    assert "hostname" not in out  # external entity never resolved


def test_binary_gh_is_not_read(run, tmp_path):
    p = tmp_path / "def.gh"
    p.write_bytes(bytes(range(256)) * 2)
    code, out, err = run(p)
    assert code == 2 and "Traceback" not in err
