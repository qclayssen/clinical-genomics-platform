process BWAMEM2_ALIGN {
    tag   { meta.id }
    label 'process_high'
    container 'quay.io/biocontainers/mulled-v2-e5d375990341c5aef3c9aff74f96f66f65375ef6:2cdf6bf1e92acbeb9b2834b1c58754167173a410-0'

    publishDir { "${params.outdir}/${meta.id}/align" }, mode: 'copy', pattern: '*.log'

    input:
    tuple val(meta), path(reads)
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.sorted.bam"), emit: bam
    path  "${meta.id}.bwamem2.log",                 emit: log

    script:
    def rg = "@RG\\tID:${meta.id}\\tSM:${meta.id}\\tPL:ILLUMINA\\tLB:${meta.id}"
    """
    bwa-mem2 mem \\
        -t ${task.cpus} \\
        -R "${rg}" \\
        ${fasta} ${reads[0]} ${reads[1]} 2> ${meta.id}.bwamem2.log \\
    | samtools sort -@ ${task.cpus} -o ${meta.id}.sorted.bam -
    samtools index ${meta.id}.sorted.bam
    """

    stub:
    """
    touch ${meta.id}.sorted.bam ${meta.id}.sorted.bam.bai ${meta.id}.bwamem2.log
    """
}
