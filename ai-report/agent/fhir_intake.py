"""Minimal HL7 FHIR genomics intake.

Maps a **subset** of the HL7 FHIR Genomics Reporting Implementation Guide's
(http://hl7.org/fhir/uv/genomics-reporting/) `Observation` component codes
to this agent's `Variant` shape (`agent.react.Variant`). This is deliberately
**not** a conformant FHIR profile validator or a full implementation of the
IG — it recognizes five real LOINC component codes (chromosome, allele
start position, ref allele, alt allele, gene studied) plus one for zygosity,
enough to drive `DeterministicInterpreter`/`ReActAgent`, and nothing more.
Anything else in the resource (identifiers, subject, performer, other
components) is ignored rather than validated.

Recognized components (LOINC codes from the Genomics Reporting IG):
  48000-4   Chromosome [Identifier] in Blood or Tissue by Molgen
  81254-5   Genomic allele start-end (used here as a single start position)
  69547-8   Genomic ref allele [ID]
  69551-0   Genomic alt allele [ID]
  48018-6   Gene studied [ID]
  53034-5   Allelic state (zygosity)

Each component is read from `valueString`, `valueInteger`, or the first
`valueCodeableConcept.coding[0].display` (falling back to `.text`) —
whichever the sender used.
"""

from __future__ import annotations

from typing import Any

from .react import Variant

CHROMOSOME_CODE = "48000-4"
ALLELE_START_CODE = "81254-5"
REF_ALLELE_CODE = "69547-8"
ALT_ALLELE_CODE = "69551-0"
GENE_STUDIED_CODE = "48018-6"
ALLELIC_STATE_CODE = "53034-5"

_DEFAULT_GENOTYPE = "heterozygous"


class FhirIntakeError(ValueError):
    """Raised when a FHIR Observation is missing a component this agent needs."""


def _component_value(component: dict[str, Any]) -> Any:
    if "valueString" in component:
        return component["valueString"]
    if "valueInteger" in component:
        return component["valueInteger"]
    if "valueCodeableConcept" in component:
        concept = component["valueCodeableConcept"]
        codings = concept.get("coding") or []
        if codings:
            return codings[0].get("display") or codings[0].get("code")
        return concept.get("text")
    return None


def _index_components(resource: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for component in resource.get("component", []):
        codings = (component.get("code") or {}).get("coding") or []
        code = next((c.get("code") for c in codings if c.get("code")), None)
        if code is not None:
            values[code] = _component_value(component)
    return values


def variant_from_fhir_observation(resource: dict[str, Any]) -> Variant:
    """Build a `Variant` from a (simplified) FHIR genomics `Observation`.

    Raises `FhirIntakeError` if the resource isn't an Observation or is
    missing one of the four components this agent cannot function without
    (chromosome, position, ref allele, alt allele). Gene and zygosity are
    optional — `Variant` already defaults them.
    """
    resource_type = resource.get("resourceType")
    if resource_type != "Observation":
        raise FhirIntakeError(f"expected a FHIR Observation resource, got {resource_type!r}")

    values = _index_components(resource)

    chrom = values.get(CHROMOSOME_CODE)
    pos = values.get(ALLELE_START_CODE)
    ref = values.get(REF_ALLELE_CODE)
    alt = values.get(ALT_ALLELE_CODE)
    gene = values.get(GENE_STUDIED_CODE) or ""
    genotype = values.get(ALLELIC_STATE_CODE) or _DEFAULT_GENOTYPE

    missing = [
        label
        for label, value in [
            (f"chromosome ({CHROMOSOME_CODE})", chrom),
            (f"allele start ({ALLELE_START_CODE})", pos),
            (f"ref allele ({REF_ALLELE_CODE})", ref),
            (f"alt allele ({ALT_ALLELE_CODE})", alt),
        ]
        if not value
    ]
    if missing:
        raise FhirIntakeError(
            "FHIR Observation is missing required genomics component(s): " + ", ".join(missing)
        )

    try:
        pos_int = int(pos)
    except (TypeError, ValueError):
        raise FhirIntakeError(
            f"allele start component ({ALLELE_START_CODE}) must be an integer, got {pos!r}"
        ) from None

    return Variant(
        chrom=str(chrom),
        pos=pos_int,
        ref=str(ref),
        alt=str(alt),
        gene=str(gene),
        genotype=str(genotype).lower(),
    )
