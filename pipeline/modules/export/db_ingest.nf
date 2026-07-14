process DB_INGEST {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/psycopg2:2.9.9'

    input:
    tuple val(meta), path(json)
    tuple val(meta2), path(vcf), path(tbi)

    output:
    tuple val(meta), path("${meta.id}.ingest.log"), emit: log

    script:
    """
    ingest_metrics.py \\
        --db-url "${params.db_url}" \\
        --metrics '${json}' \\
        --vcf '${vcf}' \\
        --log '${meta.id}.ingest.log'
    """

    stub:
    """
    echo "stub: would ingest ${meta.id} into ${params.db_url}" > ${meta.id}.ingest.log
    """
}
