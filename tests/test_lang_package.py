"""The shared expression-language package tricc_oo/lang/ (feature/20261125-expression-languages.md §3)."""

import hashlib
import os
import shutil
import subprocess

import pytest

from tricc_oo.converters.lang import LANG_DIR, lang_version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: upstream files kept untouched: HL7 cqframework tag v5.7.0, Apache KIE drools 10.2.0
UPSTREAM_SHA256 = {
    "cql/cql.g4": "517d9fa780de80f49a2a3f234e56e4b6dda5f04cb22fe31c89e7ee31811dbba1",
    "cql/fhirpath.g4": "54324384cb009c51379ab0327dbe6dad67a1ee99a6206c8103f74a8359e90627",
    "feel/FEEL_1_1.g4": "24894fb287f3eef1256cc3bb94b2991e098cbf3b4ca78508b77471dfd62fcdde",
}

GENERATED = [
    "cql/tricc_cqlLexer.py",
    "cql/tricc_cqlParser.py",
    "cql/tricc_cqlVisitor.py",
    "cql/cqlLexer.py",
    "cql/cqlParser.py",
    "cql/cqlVisitor.py",
    "feel/tricc_feelLexer.py",
    "feel/TriccFeelParser.py",
    "feel/TriccFeelParserVisitor.py",
]


@pytest.mark.parametrize("path", sorted(UPSTREAM_SHA256))
def test_upstream_grammar_untouched(path):
    with open(os.path.join(LANG_DIR, path), "rb") as file:
        assert hashlib.sha256(file.read()).hexdigest() == UPSTREAM_SHA256[path]


def test_version_is_semver():
    parts = lang_version().split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


@pytest.mark.parametrize("path", GENERATED)
def test_generated_parser_header(path):
    with open(os.path.join(ROOT, "tricc_oo", "converters", path), encoding="utf-8") as file:
        head = [file.readline() for _ in range(3)]
    assert head[0].strip() == "# flake8: noqa"
    assert head[1].strip() == f"# tricc-lang {lang_version()} (tricc_oo/lang/VERSION)"
    assert head[2].startswith("# Generated from ") and head[2].strip().endswith("by ANTLR 4.13.2")


def test_package_data_ships_the_folder():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as file:
        assert '"tricc_oo.lang" = ["**/*"]' in file.read()


@pytest.mark.skipif(
    shutil.which("java") is None or not os.environ.get("TRICC_CHECK_PARSER_DRIFT"),
    reason="needs Java and TRICC_CHECK_PARSER_DRIFT=1 (regenerates every parser)",
)
def test_generated_parsers_do_not_drift():
    result = subprocess.run(
        [os.path.join(ROOT, "scripts", "generate-lang-parsers.sh"), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
