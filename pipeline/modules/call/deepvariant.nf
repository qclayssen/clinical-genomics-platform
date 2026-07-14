process DEEPVARIANT {
    tag   { meta.id }
    label 'process_high'
    container 'google/deepvariant:1.6.1'

    publishDir { "${params.outdir}/${meta.id}/variants" }, mode: 'copy'

    input:
    tuple val(meta), path(bam)
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.dv.vcf.gz"), path("${meta.id}.dv.vcf.gz.tbi"), emit: vcf

    script:
    """
    samtools faidx ${fasta}
    /opt/deepvariant/bin/run_deepvariant \\
        --model_type=WGS \\
        --ref=${fasta} \\
        --reads=${bam} \\
        --regions=${params.intervals ?: 'chr20'} \\
        --output_vcf=${meta.id}.dv.vcf.gz \\
        --num_shards=${task.cpus}
    """

    stub:
    """
    echo '##fileformat=VCFv4.2' | bgzip > ${meta.id}.dv.vcf.gz
    touch ${meta.id}.dv.vcf.gz.tbi
    """
}
