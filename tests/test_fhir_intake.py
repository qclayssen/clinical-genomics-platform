"""Tests for the minimal HL7 FHIR genomics intake (ai-report/agent/fhir_intake.py)."""

import sys
from pathlib import Path

import pytest

_AI_REPORT_DIR = Path(__file__).resolve().parents[1] / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

from agent.fhir_intake import FhirIntakeError, variant_from_fhir_observation  # noqa: E402


def _observation(**component_overrides) -> dict:
    components = {
        "48000-4": {"code": {"coding": [{"code": "48000-4"}]}, "valueString": "chr20"},
        "81254-5": {"code": {"coding": [{"code": "81254-5"}]}, "valueInteger": 4699605},
        "69547-8": {"code": {"coding": [{"code": "69547-8"}]}, "valueString": "G"},
        "69551-0": {"code": {"coding": [{"code": "69551-0"}]}, "valueString": "A"},
        "48018-6": {"code": {"coding": [{"code": "48018-6"}]}, "valueString": "PRNP"},
        "53034-5": {
            "code": {"coding": [{"code": "53034-5"}]},
            "valueCodeableConcept": {"coding": [{"display": "heterozygous"}]},
        },
    }
    components.update(component_overrides)
    return {"resourceType": "Observation", "component": list(components.values())}


def test_parses_a_complete_genomics_observation():
    variant = variant_from_fhir_observation(_observation())
    assert variant.chrom == "chr20"
    assert variant.pos == 4699605
    assert variant.ref == "G"
    assert variant.alt == "A"
    assert variant.gene == "PRNP"
    assert variant.genotype == "heterozygous"


def test_gene_and_zygosity_are_optional():
    obs = _observation()
    obs["component"] = [c for c in obs["component"] if c["code"]["coding"][0]["code"] not in ("48018-6", "53034-5")]
    variant = variant_from_fhir_observation(obs)
    assert variant.gene == ""
    assert variant.genotype == "heterozygous"  # falls back to the default


def test_rejects_non_observation_resource():
    with pytest.raises(FhirIntakeError, match="expected a FHIR Observation"):
        variant_from_fhir_observation({"resourceType": "Patient"})


def test_rejects_missing_required_components():
    obs = _observation()
    obs["component"] = [c for c in obs["component"] if c["code"]["coding"][0]["code"] != "69551-0"]
    with pytest.raises(FhirIntakeError, match="alt allele"):
        variant_from_fhir_observation(obs)


def test_rejects_non_integer_position():
    obs = _observation(**{"81254-5": {"code": {"coding": [{"code": "81254-5"}]}, "valueString": "not-a-number"}})
    with pytest.raises(FhirIntakeError, match="must be an integer"):
        variant_from_fhir_observation(obs)
