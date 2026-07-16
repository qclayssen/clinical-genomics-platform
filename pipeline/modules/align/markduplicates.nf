process MARKDUPLICATES {
    tag   { meta.id }
    label 'process_medium'
    container 'quay.io/biocontainers/gatk4:4.5.0.0--py36hdfd78af_0'

    input:
    tuple val(meta), path(bam)

    output:
    tuple val(meta), path("${meta.id}.markdup.bam"), path("${meta.id}.markdup.{bai,bam.bai}"), emit: bam
    tuple val(meta), path("${meta.id}.markdup.metrics"),                                       emit: metrics
    path  "versions.yml",                                                                      emit: versions

    script:
    """
    gatk --java-options "-Xmx${task.memory.toGiga()}g" MarkDuplicates \\
        --INPUT ${bam} \\
        --OUTPUT ${meta.id}.markdup.bam \\
        --METRICS_FILE ${meta.id}.markdup.metrics \\
        --CREATE_INDEX true

    printf '"%s":\\n    gatk4: %s\\n' "${task.process}" "\$(gatk --version 2>&1 | grep -oE 'v[0-9.]+' | head -1 | sed 's/v//')" > versions.yml
    """

    stub:
    """
    touch ${meta.id}.markdup.bam ${meta.id}.markdup.bai
    printf 'LIBRARY\\tPERCENT_DUPLICATION\\n${meta.id}\\t0.05\\n' > ${meta.id}.markdup.metrics
    printf '"%s":\\n    gatk4: 4.5.0.0\\n' "${task.process}" > versions.yml
    """
}
