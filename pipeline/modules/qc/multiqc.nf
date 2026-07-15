process MULTIQC {
    label 'process_low'
    container 'quay.io/biocontainers/multiqc:1.21--pyhdfd78af_0'

    input:
    path '*'
    path multiqc_config

    output:
    path "multiqc_report.html", emit: report
    path "multiqc_data",        emit: data
    path "versions.yml",        emit: versions

    script:
    """
    multiqc --force \\
        --title "Clinical Genomics Insight Platform" \\
        --config '${multiqc_config}' \\
        .

    printf '"%s":\\n    multiqc: %s\\n' "${task.process}" "\$(multiqc --version | sed 's/.*version //')" > versions.yml
    """

    stub:
    """
    mkdir multiqc_data
    touch multiqc_report.html
    printf '"%s":\\n    multiqc: 1.21\\n' "${task.process}" > versions.yml
    """
}
