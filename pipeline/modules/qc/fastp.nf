process FASTP {
    tag   { meta.id }
    label 'process_medium'
    container 'quay.io/biocontainers/fastp:0.23.4--hadf994f_2'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("${meta.id}.trim_{1,2}.fastq.gz"), emit: reads
    path  "${meta.id}.fastp.json",                            emit: json
    path  "${meta.id}.fastp.html",                            emit: html
    path  "versions.yml",                                     emit: versions

    script:
    // Select fastp parameters based on attempt number (retry profile)
    def attempt = task.attempt
    def phred = attempt == 1 ? (params.fastp_phred_1 ?: 15) :
                attempt == 2 ? (params.fastp_phred_2 ?: 20) :
                               (params.fastp_phred_3 ?: 25)
    def min_len = attempt == 1 ? (params.fastp_length_1 ?: 50) :
                  attempt == 2 ? (params.fastp_length_2 ?: 60) :
                                 (params.fastp_length_3 ?: 75)
    def poly_g = attempt == 1 ? (params.fastp_poly_g_1 ?: false) :
                 attempt == 2 ? (params.fastp_poly_g_2 ?: true) :
                                (params.fastp_poly_g_3 ?: true)
    def cut_front = attempt >= 3 ? (params.fastp_cut_front_3 ?: true) : false
    def cut_tail  = attempt >= 3 ? (params.fastp_cut_tail_3 ?: true) : false
    def cut_window = attempt >= 3 ? (params.fastp_cut_window_3 ?: 4) : 0
    def cut_mean_q = attempt >= 3 ? (params.fastp_cut_mean_q_3 ?: 20) : 0

    // Build optional flags
    def poly_g_flag = poly_g ? '--trim_poly_g' : ''
    def cut_front_flag = cut_front ? '--cut_front' : ''
    def cut_tail_flag = cut_tail ? '--cut_tail' : ''
    def cut_window_flag = (cut_front || cut_tail) && cut_window > 0 ? "--cut_window_size ${cut_window}" : ''
    def cut_mean_flag = (cut_front || cut_tail) && cut_mean_q > 0 ? "--cut_mean_quality ${cut_mean_q}" : ''

    """
    echo "FASTP retry profile: attempt=${attempt} phred=${phred} min_len=${min_len}" >&2

    fastp \\
        --in1 ${reads[0]} --in2 ${reads[1]} \\
        --out1 ${meta.id}.trim_1.fastq.gz --out2 ${meta.id}.trim_2.fastq.gz \\
        --detect_adapter_for_pe \\
        --qualified_quality_phred ${phred} \\
        --length_required ${min_len} \\
        ${poly_g_flag} \\
        ${cut_front_flag} \\
        ${cut_tail_flag} \\
        ${cut_window_flag} \\
        ${cut_mean_flag} \\
        --thread ${task.cpus} \\
        --json ${meta.id}.fastp.json \\
        --html ${meta.id}.fastp.html

    printf '"%s":\\n    fastp: %s\\n' "${task.process}" "\$(fastp --version 2>&1 | sed 's/fastp //')" > versions.yml
    """

    stub:
    """
    touch ${meta.id}.trim_1.fastq.gz ${meta.id}.trim_2.fastq.gz
    echo '{"summary":{"after_filtering":{"q30_rate":0.92}},"filtering_result":{"passed_filter_reads":950000,"low_quality_reads":30000,"too_many_N_reads":5000,"too_short_reads":15000,"too_long_reads":0}}' > ${meta.id}.fastp.json
    touch ${meta.id}.fastp.html
    printf '"%s":\\n    fastp: 0.23.4\\n' "${task.process}" > versions.yml
    """
}
