process JSON_METRICS {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/python:3.11'

    input:
    tuple val(meta), path(dup_metrics), path(happy_summary)
    val   provenance

    output:
    tuple val(meta), path("${meta.id}.metrics.json"), emit: json
    path  "versions.yml",                             emit: versions

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

    printf '"%s":\\n    python: %s\\n' "${task.process}" "\$(python3 --version | sed 's/Python //')" > versions.yml
    """

    stub:
    """
    echo '{"sample":"${meta.id}","stub":true}' > ${meta.id}.metrics.json
    printf '"%s":\\n    python: 3.11\\n' "${task.process}" > versions.yml
    """
}
