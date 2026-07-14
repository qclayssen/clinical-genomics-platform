process HAPLOTYPECALLER {
    tag   { meta.id }
    label 'process_high'
    container 'quay.io/biocontainers/gatk4:4.5.0.0--py36hdfd78af_0'

    publishDir { "${params.outdir}/${meta.id}/variants" }, mode: 'copy'

    input:
    tuple val(meta), path(bam)
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.gatk.vcf.gz"), path("${meta.id}.gatk.vcf.gz.tbi"), emit: vcf

    script:
    """
    samtools faidx ${fasta}
    gatk CreateSequenceDictionary -R ${fasta} 2>/dev/null || true

    gatk --java-options "-Xmx${task.memory.toGiga()}g" HaplotypeCaller \\
        --input ${bam} \\
        --reference ${fasta} \\
        --output ${meta.id}.gatk.vcf.gz \\
        --intervals ${params.intervals ?: 'chr20'}
    """

    stub:
    """
    echo '##fileformat=VCFv4.2' | bgzip > ${meta.id}.gatk.vcf.gz
    touch ${meta.id}.gatk.vcf.gz.tbi
    """
}
