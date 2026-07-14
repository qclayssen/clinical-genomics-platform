process MARKDUPLICATES {
    tag   { meta.id }
    label 'process_medium'
    container 'quay.io/biocontainers/gatk4:4.5.0.0--py36hdfd78af_0'

    publishDir { "${params.outdir}/${meta.id}/align" }, mode: 'copy'

    input:
    tuple val(meta), path(bam)

    output:
    tuple val(meta), path("${meta.id}.markdup.bam"),     emit: bam
    tuple val(meta), path("${meta.id}.markdup.metrics"), emit: metrics

    script:
    """
    gatk --java-options "-Xmx${task.memory.toGiga()}g" MarkDuplicates \\
        --INPUT ${bam} \\
        --OUTPUT ${meta.id}.markdup.bam \\
        --METRICS_FILE ${meta.id}.markdup.metrics \\
        --CREATE_INDEX true
    """

    stub:
    """
    touch ${meta.id}.markdup.bam ${meta.id}.markdup.bai
    printf 'LIBRARY\\tPERCENT_DUPLICATION\\n${meta.id}\\t0.05\\n' > ${meta.id}.markdup.metrics
    """
}
