process JSON_METRICS {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/python:3.11'

    input:
    tuple val(meta), path(dup_metrics), path(happy_summary), path(reads)
    val   provenance
    path  reference
    path  truth_vcf
    path  truth_bed
    // Staged under a fixed name so it can't collide with this process's own versions.yml
    path  caller_versions, stageAs: 'caller_versions.yml'

    output:
    tuple val(meta), path("${meta.id}.metrics.json"), emit: json
    path  "versions.yml",                             emit: versions

    script:
    // provenance is a Groovy map — serialise to a shell-safe JSON string
    def prov_json = groovy.json.JsonOutput.toJson(provenance + [ sample: meta.id, caller: meta.caller ])
    // Every artifact a result is benchmarked against gets checksummed — raw reads,
    // reference and truth set, not just the two derived outputs — see docs/VALIDATION.md §6.
    def read_files = (reads instanceof List ? reads : [reads]).join(',')
    """
    build_metrics.py \\
        --sample '${meta.id}' \\
        --dup-metrics '${dup_metrics}' \\
        --happy-summary '${happy_summary}' \\
        --provenance '${prov_json}' \\
        --inputs '${dup_metrics},${happy_summary},${read_files},${reference},${truth_vcf},${truth_bed}' \\
        --caller-versions caller_versions.yml \\
        --output '${meta.id}.metrics.json'

    printf '"%s":\\n    python: %s\\n' "${task.process}" "\$(python3 --version | sed 's/Python //')" > versions.yml
    """

    stub:
    """
    echo '{"sample":"${meta.id}","stub":true}' > ${meta.id}.metrics.json
    printf '"%s":\\n    python: 3.11\\n' "${task.process}" > versions.yml
    """
}
