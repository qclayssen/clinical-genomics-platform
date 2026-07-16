process BWAMEM2_ALIGN {
    tag   { meta.id }
    label 'process_high'
    container 'quay.io/biocontainers/mulled-v2-e5d375990341c5aef3c9aff74f96f66f65375ef6:2cdf6bf1e92acbeb9b2834b1c58754167173a410-0'

    input:
    tuple val(meta), path(reads)
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.sorted.bam"), emit: bam
    path  "${meta.id}.bwamem2.log",                 emit: log
    path  "versions.yml",                           emit: versions

    script:
    def rg = "@RG\\tID:${meta.id}\\tSM:${meta.id}\\tPL:ILLUMINA\\tLB:${meta.id}"
    """
    # Build index on the fly if not already present
    if [ ! -f ${fasta}.bwt.2bit.64 ]; then
        bwa-mem2 index ${fasta}
    fi

    bwa-mem2 mem \\
        -t ${task.cpus} \\
        -R "${rg}" \\
        ${fasta} ${reads[0]} ${reads[1]} 2> ${meta.id}.bwamem2.log \\
    | samtools sort -@ ${task.cpus} -o ${meta.id}.sorted.bam -
    samtools index ${meta.id}.sorted.bam

    printf '"%s":\\n    bwa-mem2: %s\\n    samtools: %s\\n' "${task.process}" "\$(bwa-mem2 version 2>&1 | tail -1)" "\$(samtools --version | head -1 | sed 's/samtools //')" > versions.yml
    """

    stub:
    """
    touch ${meta.id}.sorted.bam ${meta.id}.sorted.bam.bai ${meta.id}.bwamem2.log
    printf '"%s":\\n    bwa-mem2: 2.2.1\\n    samtools: 1.19\\n' "${task.process}" > versions.yml
    """
}
