process QC_EVALUATE {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/python:3.11@sha256:b322907f8e52b2055ccad4e46848d28a4a5631b403116cc80ddf61ec8601e05e'

    input:
    tuple val(meta), path(fastp_json), path(dup_metrics), path(happy_summary)
    path  thresholds_config

    output:
    tuple val(meta), path("${meta.id}.qc_warnings.json"), emit: warnings
    path  "versions.yml",                                  emit: versions

    script:
    """
    qc_evaluate.py \\
        --sample '${meta.id}' \\
        --fastp-json '${fastp_json}' \\
        --dup-metrics '${dup_metrics}' \\
        --happy-summary '${happy_summary}' \\
        --thresholds-config '${thresholds_config}' \\
        --output '${meta.id}.qc_warnings.json'

    printf '"%s":\\n    python: %s\\n' "${task.process}" "\$(python3 --version | sed 's/Python //')" > versions.yml
    """

    stub:
    """
    echo '{"sample":"${meta.id}","overall_status":"pass","metrics":{},"warnings":[],"failures":[]}' > ${meta.id}.qc_warnings.json
    printf '"%s":\\n    python: 3.11\\n' "${task.process}" > versions.yml
    """
}
