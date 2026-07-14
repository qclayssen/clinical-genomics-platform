process JSON_METRICS {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/python:3.11'

    publishDir "${params.outdir}/${meta.id}/export", mode: 'copy'

    input:
    tuple val(meta), path(dup_metrics), path(happy_summary)
    val   provenance

    output:
    tuple val(meta), path("${meta.id}.metrics.json"), emit: json

    script:
    // provenance is a Groovy map — serialise to a shell-safe JSON string
    def prov_json = groovy.json.JsonOutput.toJson(provenance + [ sample: meta.id, caller: meta.caller ])
    """
    build_metrics.py \\
        --sample '${meta.id}' \\
        --dup-metrics '${dup_metrics}' \\
        --happy-summary '${happy_summary}' \\
        --provenance '${prov_json}' \\
        --inputs '${dup_metrics},${happy_summary}' \\
        --output '${meta.id}.metrics.json'
    """

    stub:
    """
    echo '{"sample":"${meta.id}","stub":true}' > ${meta.id}.metrics.json
    """
}
