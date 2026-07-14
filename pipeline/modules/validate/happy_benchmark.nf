process HAPPY_BENCHMARK {
    tag   { meta.id }
    label 'process_medium'
    container 'quay.io/biocontainers/hap.py:0.3.15--py27h5c5a762_0'

    publishDir "${params.outdir}/${meta.id}/validation", mode: 'copy'

    input:
    tuple val(meta), path(vcf), path(tbi)
    path  truth_vcf
    path  truth_bed
    tuple path(fasta), path(index)

    output:
    tuple val(meta), path("${meta.id}.happy.summary.csv"), emit: summary
    path  "${meta.id}.happy.extended.csv",                 emit: extended
    path  "${meta.id}.happy.*",                            emit: all

    script:
    """
    samtools faidx ${fasta}
    hap.py \\
        ${truth_vcf} \\
        ${vcf} \\
        -f ${truth_bed} \\
        -r ${fasta} \\
        -o ${meta.id}.happy \\
        --threads ${task.cpus} \\
        --engine vcfeval
    """

    stub:
    """
    printf 'Type,METRIC.Precision,METRIC.Recall,METRIC.F1_Score\\nSNP,0.9985,0.9971,0.9978\\nINDEL,0.9932,0.9910,0.9921\\n' > ${meta.id}.happy.summary.csv
    touch ${meta.id}.happy.extended.csv ${meta.id}.happy.roc.all.csv.gz
    """
}
