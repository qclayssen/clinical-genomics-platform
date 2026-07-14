# GA4GH standards alignment

The [Global Alliance for Genomics and Health (GA4GH)](https://www.ga4gh.org/our-products/)
publishes the interoperability standards that clinical/​research genomics platforms are
increasingly expected to speak. This page maps the platform to the relevant GA4GH products and
is **honest about status** — most are alignment/aspiration, one is actually implemented.

Status legend: **Implemented** (code + tests) · **Partial** (primitive built, not fully wired
or not fully spec-compliant) · **Aspirational** (designed-for, documented, not built) ·
**N/A here** (needs real patient data / controlled access, out of scope for a public-data
portfolio).

| GA4GH standard | What it is | Relevance here | Status |
|---|---|---|---|
| **refget** | Reference sequences addressed by a content checksum, not a name | Identify the reference by content (`ga4gh:SQ.<sha512t24u>`), strengthening provenance beyond a build label | **Implemented** — `pipeline/bin/ga4gh_ids.py`, spec known-answer test |
| **VRS** (Variation Representation Spec) | Collision-resistant, content-based IDs for variants | Give each called variant a normalized `ga4gh:VA.` identifier for unambiguous exchange | **Partial** — shared `sha512t24u` primitive + a simplified allele-digest helper; full VRS needs the `ga4gh.vrs` library |
| **WES** (Workflow Execution Service) | Standard REST API to run workflows remotely | The Nextflow pipeline is a natural fit to expose behind a WES endpoint | **Aspirational** — documented as the intended API surface |
| **DRS** (Data Repository Service) | Standard API to resolve data objects by ID | The S3 data lake objects could be served as DRS IDs | **Aspirational** |
| **Phenopackets** | Machine-readable phenotype/clinical exchange format | The AI report + `metrics.json` could be emitted as a Phenopacket for downstream systems | **Aspirational** — `metrics.json` is a step toward structured, machine-readable output |
| **htsget** | Byte-range streaming of BAM/CRAM/VCF | Serve variant/alignment slices without shipping whole files | **Aspirational** |
| **service-info** | Standard endpoint describing a service | Trivial descriptor a WES/DRS deployment would expose | **Aspirational** |
| **Crypt4GH** | Encryption format for genomic files | Encrypt real patient data at rest/in transit | **N/A here** (public GIAB data) — relevant with real data |
| **Passport / AAI, Data Use Ontology** | Standardized access control + consent codes | Gate controlled-access data | **N/A here** — relevant with real, consented patient data |

## What's actually implemented

The **GA4GH `sha512t24u` digest primitive** — the content-based identifier scheme shared by
refget and VRS — is implemented dependency-free in
[`pipeline/bin/ga4gh_ids.py`](../pipeline/bin/ga4gh_ids.py) and verified against the VRS
specification's known-answer vector (`sha512t24u(b"ACGT") == "aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2"`)
in [`tests/test_ga4gh_ids.py`](../tests/test_ga4gh_ids.py).

```bash
python3 pipeline/bin/ga4gh_ids.py --fasta pipeline/assets/reference/GRCh38_chr20.fa
# chr20   ga4gh:SQ.<content-based id>   (N bp)
```

**Why this one first:** it connects directly to the project's existing provenance/traceability
theme (SHA-256 input checksums). A GA4GH refget ID identifies the reference by its *content*, so
two labs with the same sequence produce the same ID regardless of file name or source — exactly
the interoperable traceability accreditation and multi-site work depend on.

## Next integration step (not yet done)

Wire `refget_sequence_id()` into the run provenance so every `metrics.json` records the
reference's `ga4gh:SQ.` ID next to the existing `reference_build` label — see
[ADR-0010](adr/0010-ga4gh-standards-alignment.md). Full VRS allele IDs and a WES/DRS API surface
are larger follow-ups tracked there.

## Sources

- [GA4GH — Our products](https://www.ga4gh.org/our-products/)
- [VRS v2.0 approved](https://www.ga4gh.org/news_item/variation-representation-specification-vrs-v2-0-is-an-approved-ga4gh-product/)
- [VRS — Computed Identifiers](https://vrs.ga4gh.org/en/latest/conventions/computed_identifiers.html)
- [Phenopackets](https://www.ga4gh.org/product/phenopackets/)
