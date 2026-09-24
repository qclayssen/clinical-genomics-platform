process DB_INGEST {
    tag   { meta.id }
    label 'process_low'
    container 'ghcr.io/qclayssen/cgp-tools:1.0.0@sha256:9505f581a374a0dc1cec76ba7f125557c017e325e7f75fad0ba69f75bff79c8e'

    input:
    tuple val(meta), path(json), path(qc_warnings)
    tuple val(meta2), path(vcf), path(tbi)

    output:
    tuple val(meta), path("${meta.id}.ingest.log"), emit: log
    path  "versions.yml",                           emit: versions

    script:
    """
    ingest_metrics.py \\
        --db-url "${params.db_url}" \\
        --metrics '${json}' \\
        --qc-warnings '${qc_warnings}' \\
        --vcf '${vcf}' \\
        --log '${meta.id}.ingest.log'

    printf '"%s":\\n    psycopg2: %s\\n' "${task.process}" "\$(python3 -c 'import psycopg2; print(psycopg2.__version__.split()[0])')" > versions.yml
    """

    stub:
    """
    echo "stub: would ingest ${meta.id} into ${params.db_url}" > ${meta.id}.ingest.log
    printf '"%s":\\n    psycopg2: 2.9.9\\n' "${task.process}" > versions.yml
    """
}
