"""Tests for the agent evaluation harness (ADR-0032).

* Unit tests of the pure metric functions, including hand-built traces that
  hallucinate a ClinVar citation or an ungrounded evidence code (the harness
  must catch them).
* Gold-set integrity: the committed file matches the KB derivation.
* End-to-end: the harness on the deterministic backend meets every gate in
  eval_config.json. Offline — no GPU, network, or AWS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (_REPO / "ai-report", _REPO / "ai-report" / "eval"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import build_gold_set  # noqa: E402
import eval_metrics as M  # noqa: E402
import run_eval  # noqa: E402

# ═══ Helpers ══════════════════════════════════════════════════════════════════


def _clinvar_obs(sig="Pathogenic", vid="VCV000009876", hgvs_p="p.Arg468Ter"):
    return {"type": "observation", "tool_name": "query_clinvar", "tool_output": {
        "found": True, "records": [{"variant_id": vid, "clinical_significance": sig,
                                    "review_stars": 3, "hgvs_p": hgvs_p}]}}


def _clinvar_absent():
    return {"type": "observation", "tool_name": "query_clinvar",
            "tool_output": {"found": False, "records": []}}


def _gnomad_obs(af=0.0, hom=0, codes=None, found=True):
    return {"type": "observation", "tool_name": "query_gnomad", "tool_output": {
        "found": found, "af_global": af, "homozygote_count": hom,
        "acmg_frequency_codes": codes or []}}


def _result(cls, codes, summary, trace):
    return {"classification": cls, "evidence_codes": codes, "summary": summary,
            "trace": trace, "fallback_triggered": False, "backend_used": "test"}


# ═══ Label handling ═══════════════════════════════════════════════════════════


class TestLabels:
    @pytest.mark.parametrize("label,code", [
        ("Pathogenic", "P"), ("Likely Pathogenic", "LP"), ("likely_pathogenic", "LP"),
        ("Uncertain Significance", "VUS"), ("VUS", "VUS"), ("Likely Benign", "LB"),
        ("Benign", "B"), ("Likely-Benign", "LB"),
    ])
    def test_normalize(self, label, code):
        assert M.normalize_class(label) == code

    @pytest.mark.parametrize("label", [None, "", "Pathogenic-ish", "risk factor"])
    def test_normalize_invalid(self, label):
        assert M.normalize_class(label) == M.INVALID

    def test_collapse3(self):
        assert [M.collapse3(c) for c in M.CLASSES_5] == ["P/LP", "P/LP", "VUS", "LB/B", "LB/B"]
        assert M.collapse3(M.INVALID) == M.INVALID


# ═══ Classification metrics ═══════════════════════════════════════════════════


class TestClassificationMetrics:
    PAIRS = [("P", "LP"), ("P", "P"), ("B", "B"), ("LP", "VUS"), ("B", "LP")]

    def test_accuracy(self):
        assert M.accuracy(self.PAIRS) == pytest.approx(2 / 5)
        assert M.accuracy([]) is None

    def test_accuracy_3class(self):
        pairs3 = [(M.collapse3(e), M.collapse3(p)) for e, p in self.PAIRS]
        assert M.accuracy(pairs3) == pytest.approx(3 / 5)

    def test_per_class(self):
        pc = M.per_class_accuracy(self.PAIRS, M.CLASSES_5)
        assert pc["P"] == {"n": 2, "correct": 1, "accuracy": 0.5}
        assert pc["B"] == {"n": 2, "correct": 1, "accuracy": 0.5}
        assert pc["VUS"]["accuracy"] is None

    def test_confusion_matrix(self):
        cm = M.confusion_matrix(self.PAIRS + [("VUS", "garbage")], M.CLASSES_5)
        assert cm["P"]["LP"] == 1 and cm["P"]["P"] == 1
        assert cm["B"]["LP"] == 1
        assert cm["VUS"][M.INVALID] == 1
        assert sum(sum(r.values()) for r in cm.values()) == 6

    def test_opposite_direction_errors(self):
        assert M.opposite_direction_errors(self.PAIRS) == 1  # B -> LP
        assert M.opposite_direction_errors([("P", "VUS"), ("LB", "B")]) == 0


# ═══ Hallucination + grounding ════════════════════════════════════════════════


class TestHallucination:
    def test_clean_citation_passes(self):
        facts = M.extract_tool_facts([_clinvar_obs()])
        summary = "ClinVar reports this variant as Pathogenic (VCV000009876)."
        assert M.find_hallucinated_citations(summary, facts) == []

    def test_numeric_clinvar_id_matches_returned_vcv(self):
        facts = M.extract_tool_facts([_clinvar_obs()])
        assert M.find_hallucinated_citations("See ClinVar ID 9876.", facts) == []

    def test_fabricated_accession_detected(self):
        facts = M.extract_tool_facts([_clinvar_obs()])
        issues = M.find_hallucinated_citations("Also reported as VCV000123456.", facts)
        assert len(issues) == 1 and "VCV000123456" in issues[0]

    def test_fabricated_numeric_id_detected(self):
        facts = M.extract_tool_facts([_clinvar_obs()])
        assert M.find_hallucinated_citations("ClinVar ID: 424242", facts)

    def test_accession_without_any_tool_call_detected(self):
        facts = M.extract_tool_facts([])
        assert M.find_hallucinated_citations("RCV000012345 supports this.", facts)

    def test_significance_claim_without_record_detected(self):
        facts = M.extract_tool_facts([_clinvar_absent(), _gnomad_obs()])
        issues = M.find_hallucinated_citations(
            "ClinVar reports this variant as Likely Pathogenic.", facts)
        assert issues and "no ClinVar record" in issues[0]

    def test_significance_claim_contradicting_tool_detected(self):
        facts = M.extract_tool_facts([_clinvar_obs(sig="Benign")])
        assert M.find_hallucinated_citations("ClinVar classifies it as Pathogenic.", facts)

    def test_deterministic_interpreter_trace_shape(self):
        # DeterministicInterpreter flattens the ClinVar observation (no records list)
        trace = [{"type": "observation", "tool_name": "query_clinvar",
                  "tool_output": {"clinical_significance": "Benign", "review_stars": 3}}]
        facts = M.extract_tool_facts(trace)
        assert facts["clinvar_found"] and facts["clinvar_sigs"] == {"B"}
        assert M.find_hallucinated_citations("ClinVar reports this variant as Benign.", facts) == []


class TestGrounding:
    def test_all_grounded(self):
        facts = M.extract_tool_facts([_clinvar_obs(), _gnomad_obs(af=0.0, codes=["PM2"])])
        g = M.grounding(["PS1", "PP5", "PM2", "PVS1"], facts)
        assert g == {"n_codes": 4, "n_grounded": 4, "ungrounded": []}

    def test_code_no_tool_can_produce_is_ungrounded(self):
        facts = M.extract_tool_facts([_clinvar_obs(), _gnomad_obs(af=0.0)])
        assert M.grounding(["PS3", "PP3"], facts)["ungrounded"] == ["PS3", "PP3"]

    def test_clinvar_codes_without_clinvar_record_ungrounded(self):
        facts = M.extract_tool_facts([_clinvar_absent(), _gnomad_obs(af=0.0)])
        assert M.grounding(["PS1", "PM2"], facts)["ungrounded"] == ["PS1"]

    def test_pm2_contradicted_by_frequency_ungrounded(self):
        facts = M.extract_tool_facts([_gnomad_obs(af=0.001)])
        assert M.grounding(["PM2"], facts)["ungrounded"] == ["PM2"]

    def test_pm2_needs_gnomad_call(self):
        assert M.grounding(["PM2"], M.extract_tool_facts([]))["ungrounded"] == ["PM2"]

    def test_benign_frequency_codes(self):
        facts = M.extract_tool_facts([_gnomad_obs(af=0.2, hom=10)])
        assert M.grounding(["BA1", "BS1", "BS2"], facts)["ungrounded"] == []
        facts = M.extract_tool_facts([_gnomad_obs(af=0.02, hom=0)])
        assert M.grounding(["BA1", "BS2"], facts)["ungrounded"] == ["BA1", "BS2"]

    def test_pvs1_requires_truncating_hgvs(self):
        facts = M.extract_tool_facts([_clinvar_obs(hgvs_p="p.Gly277Ser")])
        assert M.grounding(["PVS1"], facts)["ungrounded"] == ["PVS1"]


# ═══ Case scoring, aggregation, thresholds ════════════════════════════════════


GOLD_ROW = {"id": "JAG1:p.Arg468Ter", "tier": "gold", "expected_class": "P"}
PROBE_ROW = {"id": "probe:x", "tier": "probe", "expected_class": None}


class TestAggregation:
    def _cases(self):
        good = _result("Likely Pathogenic", ["PS1", "PP5", "PM2"],
                       "ClinVar reports this variant as Pathogenic.",
                       [_clinvar_obs(), _gnomad_obs(af=0.0, codes=["PM2"])])
        bad = _result("Pathogenic", ["PS1", "PS3"],
                      "ClinVar reports this as Pathogenic (VCV000999999).",
                      [_clinvar_absent(), _gnomad_obs(af=0.0)])
        return [M.score_case(GOLD_ROW, good), M.score_case(PROBE_ROW, bad)]

    def test_score_case(self):
        good, bad = self._cases()
        assert good["correct_5"] is False and good["correct_3"] is True
        assert good["hallucinations"] == [] and good["queried_clinvar_and_gnomad"]
        assert bad["correct_5"] is None  # probe: no label
        assert len(bad["hallucinations"]) == 2  # fabricated VCV + significance claim
        assert bad["grounding"]["ungrounded"] == ["PS1", "PS3"]

    def test_aggregate(self):
        agg = M.aggregate(self._cases(), ["gold", "probe"])
        assert agg["n_cases"] == 2 and agg["n_labelled"] == 1
        assert agg["accuracy_5class"] == 0.0 and agg["accuracy_3class"] == 1.0
        assert agg["hallucinated_citation_rate"] == 0.5
        assert agg["tool_grounding_rate"] == pytest.approx(3 / 5)
        assert agg["fully_grounded_case_rate"] == 0.5
        gold_only = M.aggregate(self._cases(), ["gold"])
        assert gold_only["hallucinated_citation_rate"] == 0.0

    def test_check_thresholds(self):
        agg = {"accuracy_3class": 0.85, "hallucinated_citation_rate": 0.1,
               "opposite_direction_errors": 0, "tool_grounding_rate": None}
        failures = M.check_thresholds(agg, {
            "min_accuracy_3class": 0.9, "max_hallucinated_citation_rate": 0.0,
            "max_opposite_direction_errors": 0, "min_tool_grounding_rate": 0.9})
        assert len(failures) == 3
        assert any("accuracy_3class" in f for f in failures)
        assert any("tool_grounding_rate: no data" in f for f in failures)
        assert M.check_thresholds({"accuracy_3class": 0.9}, {"min_accuracy_3class": 0.9}) == []


# ═══ Gold set integrity ═══════════════════════════════════════════════════════


class TestGoldSet:
    def test_committed_gold_set_matches_kb_derivation(self):
        assert build_gold_set.main(["--check"]) == 0, (
            "gold_set.jsonl drifted from the KB — rerun ai-report/eval/build_gold_set.py")

    def test_gold_tier_criterion(self):
        rows = run_eval.load_gold_set(run_eval.DEFAULT_GOLD)
        gold = [r for r in rows if r["tier"] == "gold"]
        assert len(gold) >= 10
        for r in gold:
            assert r["review_status"] in build_gold_set.GOLD_REVIEW_STATUSES
            assert r["expected_class"] in M.CLASSES_5
            assert r["clinvar_variation_id"]

    def test_probes_have_no_label(self):
        rows = run_eval.load_gold_set(run_eval.DEFAULT_GOLD)
        probes = [r for r in rows if r["tier"] == "probe"]
        assert probes and all(r["expected_class"] is None for r in probes)


# ═══ End to end on the deterministic backend ══════════════════════════════════


@pytest.fixture(scope="module")
def det_report():
    return run_eval.run(backend="deterministic")


class TestHarnessDeterministic:
    def test_all_gates_pass(self, det_report):
        failed = [g for g in det_report["gates"] if not g["passed"]]
        assert not failed, f"gate failures: {failed}"
        assert det_report["passed"] is True

    def test_gate_thresholds_come_from_config(self, det_report):
        cfg = json.loads(run_eval.DEFAULT_CONFIG.read_text())
        assert [g["thresholds"] for g in det_report["gates"]] == [g["thresholds"] for g in cfg["gates"]]

    def test_no_hallucinated_citations_anywhere(self, det_report):
        assert det_report["summary_all"]["hallucinated_citation_rate"] == 0.0
        assert det_report["summary_all"]["opposite_direction_errors"] == 0

    def test_known_baseline(self, det_report):
        # Pins the documented baseline (README / ADR-0032); a change here must be deliberate.
        gold = det_report["by_tier"]["gold"]
        assert gold["n_cases"] == 10
        assert gold["accuracy_3class"] == pytest.approx(0.9)
        assert gold["accuracy_5class"] == pytest.approx(0.3)
        assert gold["confusion_5class"]["P"]["LP"] == 6

    def test_provenance_stamp(self, det_report):
        p = det_report["provenance"]
        assert p["gold_set_sha256"] == run_eval.sha256_file(run_eval.DEFAULT_GOLD)
        assert len(p["knowledge_base_sha256"]) == 64 and len(p["config_sha256"]) == 64
        assert p["backend"] == "deterministic" and p["model_id"] == "deterministic-v1"
        assert p["git_commit"]
        assert "clinvar_source" in p["knowledge_base_metadata"]

    def test_reproducible(self, det_report):
        again = run_eval.run(backend="deterministic")
        strip = lambda r: [{k: v for k, v in c.items()} for c in r["cases"]]  # noqa: E731
        assert strip(again) == strip(det_report)

    def test_interpreter_backend_also_passes(self):
        assert run_eval.run(backend="interpreter")["passed"] is True

    def test_cli_writes_report_and_exit_code(self, tmp_path, capsys):
        out = tmp_path / "report.json"
        assert run_eval.main(["--out", str(out)]) == 0
        data = json.loads(out.read_text())
        assert data["passed"] is True and data["results"]
        assert "OVERALL: PASS" in capsys.readouterr().out

    def test_cli_fails_on_unmet_threshold(self, tmp_path):
        cfg = json.loads(run_eval.DEFAULT_CONFIG.read_text())
        cfg["gates"][0]["thresholds"]["min_accuracy_5class"] = 0.99
        cfg_path = tmp_path / "cfg.json"
        cfg_path.write_text(json.dumps(cfg))
        assert run_eval.main(["--config", str(cfg_path), "--out", str(tmp_path / "r.json")]) == 1


def test_scripted_backend_adds_no_ungrounded_default_code():
    """Regression: with no supporting tool evidence the scripted backend must
    not invent a default PM2 (found by this harness on its first run)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-report"))
    from agent.llm import DeterministicBackend, Message  # noqa: E402

    backend = DeterministicBackend()
    msgs = [Message(role="tool", content='{"records": [], "af": null}')]
    assert backend._gather_evidence_codes(msgs) == []


def test_final_answer_empty_evidence_only_for_vus():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-report"))
    from agent.tools import _final_answer  # noqa: E402

    summary = "No ACMG criteria were met by any tool observation."
    assert _final_answer("Uncertain Significance", [], summary).get("success") is not False
    assert _final_answer("Likely Pathogenic", [], summary)["success"] is False
