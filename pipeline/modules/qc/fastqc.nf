process FASTQC {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0'

    publishDir { "${params.outdir}/${meta.id}/qc/fastqc" }, mode: 'copy'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("*.zip"),  emit: zip
    path  "*.html",                  emit: html

    script:
    """
    fastqc --threads ${task.cpus} --quiet ${reads.join(' ')}
    """

    stub:
    """
    touch ${meta.id}_fastqc.zip ${meta.id}_fastqc.html
    """
}
