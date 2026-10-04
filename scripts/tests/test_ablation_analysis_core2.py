# scripts/tests/test_ablation_analysis_core2.py
"""The analysis understands both baselines: plain translation (the first real run, folder 20261004-045103) and Expand
(preset core2). Roles follow the folder's baseline text, lettered arm codes sort in order, the raw Vietnamese arm is a
sanity check in either folder, and the text table compares the baseline with the other English text."""
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
SCRIPTS = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(SCRIPTS))

from ablation_analysis import tables_core  # noqa: E402
from ablation_analysis.context import Ctx, natural_key  # noqa: E402
from ablation_analysis.data import ConfigInfo, RunData, config_code, role_of  # noqa: E402
from tests.test_ablation_analysis_core import result  # noqa: E402

ALL = ["beit3", "clip", "siglip2"]


def config(text, models = ALL, mode = "per_model", **more) :
    return {"models" : models, "rerank_mode" : mode, "text_policy" : text, "task_mode" : "ensemble", **more}


def test_lettered_codes_and_their_order() :
    assert [config_code(n) for n in ("C12a beit3+clip, rerank off", "C01 baseline", "T01 TRAKE-N", "C13 rerank after fusion (post-fusion rerank, our implementation)")] == ["C12a", "C01", "T01", "C13"]
    assert sorted(["C13", "C12b", "C09", "C12a", "T01", "C12c", "C02"], key = natural_key) == ["C02", "C09", "C12a", "C12b", "C12c", "C13", "T01"]


def test_roles_follow_the_text_of_the_folders_baseline() :
    expand_base = "expand_gemini"
    assert role_of(config("expand_gemini"), expand_base) == "base"
    assert role_of(config("expand_gemini", ["clip"]), expand_base) == "single:clip"
    assert role_of(config("expand_gemini", ["beit3", "clip"], "off"), expand_base) == "pair:beit3+clip:off"
    assert role_of(config("translate_gtx"), expand_base) == "plain_text"
    assert role_of(config("raw_vi"), expand_base) == "raw_vi"
    assert role_of(config("expand_gemini", subset = {"task_types" : ["TRAKE"]}), expand_base) == "trake_plain"
    # The first real run: gtx baseline, raw Vietnamese, and (preset extras) an Expand rung.
    assert role_of(config("translate_gtx")) == "base" and role_of(config("raw_vi")) == "raw_vi" and role_of(config("expand_gemini")) == "expand_gemini"
    assert role_of(config("translate_gtx", ["siglip2"], "off")) == "single:siglip2:off"


def _data(arms : dict[str, tuple[str, dict, list]]) -> RunData :
    """arms: code -> (role, config, ranks)."""
    data = RunData(folder = Path("."), results = [], configs = {}, provenance = {}, suite = {})
    for code, (role, cfg, ranks) in arms.items() :
        data.configs[code] = ConfigInfo(code, code, cfg, role, sanity = role == "raw_vi")
        for i, rank in enumerate(ranks) :
            r = result(code, f"q{i}", rank)
            data.results.append(r)
            data.by_code.setdefault(code, {})[r.uid] = r
    return data


def _ctx(data) :
    return Ctx(data = data, features = None, labels = None, facts = {}, out = Path("."))


def test_sanity_arm_is_out_of_the_retrieval_codes_and_in_its_own_table() :
    data = _data({
        "C01" : ("base", config("expand_gemini"), [1, 1, 2, None, 1, 3]),
        "C14" : ("plain_text", config("translate_gtx"), [1, 2, 2, None, 5, None]),
        "C15" : ("raw_vi", config("raw_vi"), [None, None, 7, None, None, 9]),
    })
    ctx = _ctx(data)
    assert ctx.retrieval_codes() == ["C01", "C14"] and ctx.sanity_codes() == ["C15"]
    (text,) = tables_core.t5_text_policy(ctx)
    labels = {row[2] for row in text.rows}
    assert labels == {"Expand (LLM-prepared English) (baseline)", "plain translation (Google Translate)"}
    assert all("raw" not in row[2] for row in text.rows)
    (sanity,) = tables_core.t5s_sanity(ctx)
    assert {row[1] for row in sanity.rows} == {"C01", "C15"}


def test_text_table_for_the_first_run_is_skipped_and_the_sanity_table_still_appears() :
    data = _data({
        "C01" : ("base", config("translate_gtx"), [1, 1, 2, None]),
        "C12" : ("raw_vi", config("raw_vi"), [None, 4, None, None]),
    })
    ctx = _ctx(data)
    assert tables_core.t5_text_policy(ctx) == [] and ctx.skipped and "no arm with a different English text" in ctx.skipped[0]
    assert len(tables_core.t5s_sanity(ctx)) == 1
