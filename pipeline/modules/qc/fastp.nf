process FASTP {
    tag   { meta.id }
    label 'process_medium'
    container 'quay.io/biocontainers/fastp:0.23.4--hadf994f_2'

    publishDir { "${params.outdir}/${meta.id}/qc/fastp" }, mode: 'copy'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("${meta.id}.trim_{1,2}.fastq.gz"), emit: reads
    path  "${meta.id}.fastp.json",                            emit: json
    path  "${meta.id}.fastp.html",                            emit: html

    script:
    """
    fastp \\
        --in1 ${reads[0]} --in2 ${reads[1]} \\
        --out1 ${meta.id}.trim_1.fastq.gz --out2 ${meta.id}.trim_2.fastq.gz \\
        --detect_adapter_for_pe \\
        --qualified_quality_phred 15 \\
        --length_required 50 \\
        --thread ${task.cpus} \\
        --json ${meta.id}.fastp.json \\
        --html ${meta.id}.fastp.html
    """

    stub:
    """
    touch ${meta.id}.trim_1.fastq.gz ${meta.id}.trim_2.fastq.gz
    echo '{"summary":{}}' > ${meta.id}.fastp.json
    touch ${meta.id}.fastp.html
    """
}
