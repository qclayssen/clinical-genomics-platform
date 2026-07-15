"""Variant calling Lambda handler.

Invokes variant caller on aligned data, supporting caller selection
(HaplotypeCaller default, DeepVariant optional). Writes VCF output
to S3 work/<run_id>/called/ and returns variant call metadata.

Receives Step Functions payload: {run_id, sample_id, qc_metrics}
"""

import gzip
import json
import logging
import os
import random
from datetime import datetime, timezone

from lambdas.shared.s3_utils import write_bytes
from lambdas.shared.timestamps import now_iso8601

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUPPORTED_CALLERS = {"HaplotypeCaller", "DeepVariant"}
DEFAULT_CALLER = "HaplotypeCaller"


def _generate_vcf_content(
    sample_id: str, caller: str, n_variants: int
) -> bytes:
    """Generate a representative VCF file with header and placeholder records.

    Args:
        sample_id: Sample identifier for the VCF header.
        caller: Name of the variant caller used.
        n_variants: Number of variant records to note in the header.

    Returns:
        Gzipped VCF content as bytes.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    vcf_lines = [
        "##fileformat=VCFv4.2",
        f"##fileDate={timestamp}",
        f"##source={caller}",
        "##reference=GRCh38",
        "##contig=<ID=chr20,length=64444167>",
        '##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">',
        '##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">',
        '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
        '##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">',
        f"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{sample_id}",
        f"# {n_variants} variant(s) called by {caller} on chr20",
        "chr20\t1000000\t.\tA\tG\t50\tPASS\tDP=30;AF=0.5\tGT:DP\t0/1:30",
    ]
    vcf_text = "\n".join(vcf_lines) + "\n"
    return gzip.compress(vcf_text.encode("utf-8"))


def handler(event: dict, context: object = None) -> dict:
    """Lambda handler for variant calling.

    Simulates variant calling on aligned data for the demo platform.
    Supports HaplotypeCaller (default) and DeepVariant caller selection.

    Args:
        event: Step Functions payload with keys:
            - run_id (str): Unique pipeline run identifier.
            - sample_id (str): Sample identifier (e.g., HG002).
            - caller (str, optional): Variant caller to use.
            - qc_metrics (dict, optional): QC metrics from previous step.
        context: Lambda context object (unused).

    Returns:
        Dict with keys: run_id, sample_id, vcf_key, caller, n_variants.

    Raises:
        ValueError: If caller is not one of the supported callers.
        KeyError: If required fields are missing from the event.
    """
    run_id = event["run_id"]
    sample_id = event["sample_id"]
    caller = event.get("caller", DEFAULT_CALLER)

    bucket = os.environ["DATA_LAKE_BUCKET"]

    log_context = {
        "timestamp": now_iso8601(),
        "level": "INFO",
        "run_id": run_id,
        "function_name": "cgp-variant-calling",
    }

    logger.info(json.dumps({**log_context, "message": "Starting variant calling", "caller": caller}))

    # Validate caller selection
    if caller not in SUPPORTED_CALLERS:
        error_msg = f"Unsupported caller '{caller}'. Must be one of: {sorted(SUPPORTED_CALLERS)}"
        logger.error(json.dumps({**log_context, "level": "ERROR", "message": error_msg}))
        raise ValueError(error_msg)

    # Simulate variant calling — generate representative variant count
    # In production this would invoke the actual caller tool on aligned BAM data
    random.seed(f"{run_id}_{caller}")
    n_variants = random.randint(70000, 95000)

    logger.info(
        json.dumps({
            **log_context,
            "message": "Variant calling complete",
            "caller": caller,
            "n_variants": n_variants,
        })
    )

    # Generate VCF content and write to S3
    vcf_key = f"work/{run_id}/called/variants.vcf.gz"
    vcf_content = _generate_vcf_content(sample_id, caller, n_variants)

    write_bytes(bucket, vcf_key, vcf_content, content_type="application/gzip")

    logger.info(
        json.dumps({
            **log_context,
            "message": "VCF written to S3",
            "vcf_key": vcf_key,
            "size_bytes": len(vcf_content),
        })
    )

    return {
        "run_id": run_id,
        "sample_id": sample_id,
        "vcf_key": vcf_key,
        "caller": caller,
        "n_variants": n_variants,
    }
