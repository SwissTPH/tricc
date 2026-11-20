"""XLSForm pages (feature/20261120-questionnaire-pages.md, phase 4).

XLSForm groups are already one level deep (a group is closed before the next one opens and
reopened under a new name) and every ``begin group`` row is a ``field-list``, so ``page``
needs no new row: a page is one screen, and a page called inside a page splits it.
"""

import glob
import os
import subprocess
import sys
import tempfile

import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_DIR = os.path.join(REPO, "tests", "data", "yaml")


def survey(fixture, output_strategy="XLSFormStrategy"):
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            [
                sys.executable, "tests/build.py", "-i", os.path.join(YAML_DIR, fixture), "-o", out,
                "-I", "YamlStrategy", "-O", output_strategy,
            ],
            cwd=REPO,
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": REPO},
        )
        (xlsx,) = glob.glob(os.path.join(out, "**", "*.xlsx"), recursive=True)
        return pd.read_excel(xlsx, sheet_name="survey").fillna("")


def group_rows(df):
    return df[df["type"] == "begin group"]


@pytest.fixture(scope="module", params=["XLSFormStrategy", "XLSFormCHTStrategy"])
def paged(request):
    return survey("xlsform_pages.yaml", request.param)


def test_page_activity_is_a_field_list(paged):
    rows = group_rows(paged)
    pages = rows[rows["name"].str.startswith(("activity_p", "activity_c", "p_extra_group"))]
    assert len(pages) == 4
    assert set(pages["appearance"]) == {"field-list"}


def test_page_inside_page_closes_and_reopens_the_outer_group(paged):
    names = list(group_rows(paged)["name"])
    outer = [n for n in names if n.startswith("activity_p")]
    inner = [n for n in names if n.startswith("activity_c")]
    assert len(outer) == 2 and len(set(outer)) == 2
    assert names.index(outer[0]) < names.index(inner[0]) < names.index(outer[1])
    # the outer group is closed before the inner one opens: no group nests in another
    depth = 0
    for kind in paged["type"]:
        if kind in ("begin group", "begin_group"):
            depth += 1
        elif kind in ("end group", "end_group"):
            depth -= 1
        if kind == "begin group":
            assert depth == 1
    # the reopened group keeps the outer relevance
    relevance = dict(zip(group_rows(paged)["name"], group_rows(paged)["relevance"]))
    assert relevance[outer[0]] == relevance[outer[1]] != ""


def test_page_group_is_shown_with_its_activity(paged):
    rows = group_rows(paged)
    relevance = dict(zip(rows["name"], rows["relevance"]))
    outer = next(n for n in rows["name"] if n.startswith("activity_p"))
    assert relevance["p_extra_group"] == relevance[outer]


@pytest.mark.parametrize("output_strategy", ["XLSFormStrategy", "XLSFormCHTStrategy"])
def test_no_page_gives_the_same_xlsform(output_strategy):
    with_pages = survey("xlsform_pages.yaml", output_strategy)
    without = survey("xlsform_no_pages.yaml", output_strategy)
    keep = [c for c in with_pages.columns if c in without.columns]
    assert with_pages[keep].equals(without[keep])


@pytest.mark.parametrize("output_strategy", ["XLSFormStrategy", "XLSFormCHTStrategy"])
def test_as_group_on_blocks_and_groups(output_strategy):
    """asGroup on blocks and groups of questions (rev. 2026-11-20)."""
    df = survey("as_group_blocks.yaml", output_strategy)
    names = list(group_rows(df)["name"])
    # a block called with asGroup: true (or whose block_start says so) gets its own group
    assert [n for n in names if n.startswith("blk_a_Ii_")]
    assert [n for n in names if n.startswith("blk_c_Ii_")]
    # inlined block: no group of its own
    assert not [n for n in names if n.startswith("blk_b_")]
    # a group of questions with asGroup: false gets none, the default one does
    assert "frame" not in names and not [n for n in names if n.startswith("frame_")]
    assert "head" in names
