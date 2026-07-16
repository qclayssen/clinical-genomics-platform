process DEEPVARIANT {
    tag   { meta.id }
    label 'process_high'
    container 'google/deepvariant:1.6.1'

    input:
    tuple val(meta), path(bam)
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.dv.vcf.gz"), path("${meta.id}.dv.vcf.gz.tbi"), emit: vcf
    path  "versions.yml",                                                            emit: versions

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

    printf '"%s":\\n    deepvariant: %s\\n' "${task.process}" "\$(/opt/deepvariant/bin/run_deepvariant --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1)" > versions.yml
    """

    stub:
    """
    printf '##fileformat=VCFv4.2\\n' | gzip > ${meta.id}.dv.vcf.gz
    touch ${meta.id}.dv.vcf.gz.tbi
    printf '"%s":\\n    deepvariant: 1.6.1\\n' "${task.process}" > versions.yml
    """
}
