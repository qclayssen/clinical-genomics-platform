#!/usr/bin/env nextflow
/*
 * Clinical Genomics Insight Platform — germline SNV pipeline (DSL2)
 *
 *   QC → align → mark duplicates → call variants → benchmark vs. truth → export
 *
 * Scope: GIAB HG002/NA24385, GRCh38 chr20. Benchmarked with hap.py against the
 * v4.2.1 high-confidence truth set. See docs/VALIDATION.md.
 */

nextflow.enable.dsl = 2

// ── Modules ────────────────────────────────────────────────────────────────
include { FASTP           } from './modules/qc/fastp.nf'
include { FASTQC          } from './modules/qc/fastqc.nf'
include { MULTIQC         } from './modules/qc/multiqc.nf'
include { BWAMEM2_ALIGN   } from './modules/align/bwamem2.nf'
include { MARKDUPLICATES  } from './modules/align/markduplicates.nf'
include { HAPLOTYPECALLER } from './modules/call/haplotypecaller.nf'
include { DEEPVARIANT     } from './modules/call/deepvariant.nf'
include { HAPPY_BENCHMARK } from './modules/validate/happy_benchmark.nf'
include { JSON_METRICS    } from './modules/export/json_metrics.nf'
include { PARQUET_EXPORT  } from './modules/export/parquet_export.nf'
include { DB_INGEST       } from './modules/export/db_ingest.nf'

// ── Provenance stamp captured once, threaded into every export ──────────────
def provenance = [
    pipeline_version : workflow.manifest.version,
    git_commit       : workflow.commitId ?: 'local-dev',
    run_id           : workflow.runName,
    started_at       : workflow.start.toString(),
    reference_build  : params.reference_build,
    truth_version    : params.truth_version
]

workflow {

    // ── Input: sample sheet -> [ meta, [fastq_1, fastq_2] ] ─────────────────
    Channel
        .fromPath(params.input, checkIfExists: true)
        .splitCsv(header: true)
        .map { row ->
            def meta = [ id: row.sample, caller: params.caller ]
            tuple(meta, [ file(row.fastq_1, checkIfExists: true),
                          file(row.fastq_2, checkIfExists: true) ])
        }
        .set { ch_reads }

    ch_reference = tuple(file(params.reference, checkIfExists: true),
                         file("${params.reference}.*"))

    // ── QC ──────────────────────────────────────────────────────────────────
    FASTP(ch_reads)
    FASTQC(FASTP.out.reads)

    // ── Align + dedup ─────────────────────────────────────────────────────────
    BWAMEM2_ALIGN(FASTP.out.reads, ch_reference)
    MARKDUPLICATES(BWAMEM2_ALIGN.out.bam)

    // ── Variant calling (caller selectable; default gatk) ─────────────────────
    if (params.caller == 'deepvariant') {
        DEEPVARIANT(MARKDUPLICATES.out.bam, ch_reference)
        ch_vcf = DEEPVARIANT.out.vcf
    } else {
        HAPLOTYPECALLER(MARKDUPLICATES.out.bam, ch_reference)
        ch_vcf = HAPLOTYPECALLER.out.vcf
    }

    // ── Analytical validation vs. GIAB truth ──────────────────────────────────
    HAPPY_BENCHMARK(
        ch_vcf,
        file(params.truth_vcf, checkIfExists: true),
        file(params.truth_bed, checkIfExists: true),
        ch_reference
    )

    // ── Structured export + provenance ────────────────────────────────────────
    JSON_METRICS(
        MARKDUPLICATES.out.metrics
            .join(HAPPY_BENCHMARK.out.summary),
        provenance
    )
    PARQUET_EXPORT(JSON_METRICS.out.json)

    if (params.db_ingest) {
        DB_INGEST(JSON_METRICS.out.json, ch_vcf)
    }

    // ── Aggregate QC report ───────────────────────────────────────────────────
    MULTIQC(
        FASTQC.out.zip
            .mix(FASTP.out.json)
            .mix(MARKDUPLICATES.out.metrics)
            .mix(HAPPY_BENCHMARK.out.summary)
            .map { it instanceof List ? it[1] : it }
            .collect()
    )
}

workflow.onComplete {
    log.info """
    ── Pipeline complete ────────────────────────────────────────────
      run name    : ${workflow.runName}
      status      : ${workflow.success ? 'SUCCESS' : 'FAILED'}
      duration    : ${workflow.duration}
      results     : ${params.outdir}
      provenance  : git ${provenance.git_commit}, ref ${params.reference_build}
    ─────────────────────────────────────────────────────────────────
    """.stripIndent()
}
