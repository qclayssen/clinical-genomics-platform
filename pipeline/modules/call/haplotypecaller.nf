process HAPLOTYPECALLER {
    tag   { meta.id }
    label 'process_high'
    container 'quay.io/biocontainers/gatk4:4.5.0.0--py36hdfd78af_0'

    input:
    tuple val(meta), path(bam)
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.gatk.vcf.gz"), path("${meta.id}.gatk.vcf.gz.tbi"), emit: vcf
    path  "versions.yml",                                                                emit: versions

    script:
    """
    gatk CreateSequenceDictionary -R ${fasta} 2>/dev/null || true

    gatk --java-options "-Xmx${task.memory.toGiga()}g" HaplotypeCaller \\
        --input ${bam} \\
        --reference ${fasta} \\
        --output ${meta.id}.gatk.vcf.gz \\
        --intervals ${params.intervals ?: 'chr20'}

    printf '"%s":\\n    gatk4: %s\\n' "${task.process}" "\$(gatk --version 2>&1 | grep -oE 'v[0-9.]+' | head -1 | sed 's/v//')" > versions.yml
    """

    stub:
    """
    echo '##fileformat=VCFv4.2' | bgzip > ${meta.id}.gatk.vcf.gz
    touch ${meta.id}.gatk.vcf.gz.tbi
    printf '"%s":\\n    gatk4: 4.5.0.0\\n' "${task.process}" > versions.yml
    """
}
