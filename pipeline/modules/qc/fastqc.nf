process FASTQC {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("*.zip"),  emit: zip
    path  "*.html",                  emit: html
    path  "versions.yml",            emit: versions

    script:
    """
    fastqc --threads ${task.cpus} --quiet ${reads.join(' ')}

    printf '"%s":\\n    fastqc: %s\\n' "${task.process}" "\$(fastqc --version | sed 's/FastQC v//')" > versions.yml
    """

    stub:
    """
    touch ${meta.id}_fastqc.zip ${meta.id}_fastqc.html
    printf '"%s":\\n    fastqc: 0.12.1\\n' "${task.process}" > versions.yml
    """
}
