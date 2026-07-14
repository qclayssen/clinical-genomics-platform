# Citations

The Clinical Genomics Insight Platform builds on open-source tools, reference materials, and
community standards. If this project or its methodology is useful to you, please also credit
the work below. This is a portfolio project, not an accredited clinical test — see the scope
note in [`README.md`](README.md).

## Pipeline framework and community conventions

- **Nextflow**

  > Di Tommaso P, Chatzou M, Floden EW, Barja PP, Palumbo E, Notredame C. Nextflow enables
  > reproducible computational workflows. Nat Biotechnol. 2017;35(4):316-319.
  > doi: [10.1038/nbt.3820](https://doi.org/10.1038/nbt.3820). <https://www.nextflow.io/>

- **nf-core** (module structure, config, and lint conventions this repo follows)

  > Ewels PA, Peltzer A, Fillinger S, Patel H, Alneberg J, Wilm A, Garcia MU, Di Tommaso P,
  > Nahnsen S. The nf-core framework for community-curated bioinformatics pipelines.
  > Nat Biotechnol. 2020;38(3):276-278.
  > doi: [10.1038/s41587-020-0439-x](https://doi.org/10.1038/s41587-020-0439-x). <https://nf-co.re/>

## Quality control

- **fastp** — adapter/quality trimming of paired-end reads (`modules/qc/fastp.nf`)

  > Chen S, Zhou Y, Chen Y, Gu J. fastp: an ultra-fast all-in-one FASTQ preprocessor.
  > Bioinformatics. 2018;34(17):i884-i890.
  > doi: [10.1093/bioinformatics/bty560](https://doi.org/10.1093/bioinformatics/bty560).
  > <https://github.com/OpenGene/fastp>

- **FastQC** — per-sample read quality metrics (`modules/qc/fastqc.nf`)

  > Andrews S. FastQC: A Quality Control Tool for High Throughput Sequence Data. 2010.
  > <https://www.bioinformatics.babraham.ac.uk/projects/fastqc/>

- **MultiQC** — aggregate QC report across tools/samples (`modules/qc/multiqc.nf`)

  > Ewels P, Magnusson M, Lundin S, Käller M. MultiQC: summarize analysis results for multiple
  > tools and samples in a single report. Bioinformatics. 2016;32(19):3047-3048.
  > doi: [10.1093/bioinformatics/btw354](https://doi.org/10.1093/bioinformatics/btw354).
  > <https://multiqc.info/>

## Alignment and duplicate marking

- **BWA-MEM2** — read alignment to GRCh38 (`modules/align/bwamem2.nf`)

  > Vasimuddin Md, Misra S, Li H, Aluru S. Efficient Architecture-Aware Acceleration of BWA-MEM
  > for Multicore Systems. IEEE IPDPS. 2019:314-324.
  > doi: [10.1109/IPDPS.2019.00041](https://doi.org/10.1109/IPDPS.2019.00041).
  > <https://github.com/bwa-mem2/bwa-mem2>

- **SAMtools** — BAM sort/index within the alignment step (`modules/align/bwamem2.nf`)

  > Danecek P, Bonfield JK, Liddle J, et al. Twelve years of SAMtools and BCFtools.
  > GigaScience. 2021;10(2):giab008.
  > doi: [10.1093/gigascience/giab008](https://doi.org/10.1093/gigascience/giab008).
  > <https://www.htslib.org/>

- **GATK4 / Picard MarkDuplicates** — duplicate marking (`modules/align/markduplicates.nf`)

  > McKenna A, Hanna M, Banks E, et al. The Genome Analysis Toolkit: a MapReduce framework for
  > analyzing next-generation DNA sequencing data. Genome Res. 2010;20(9):1297-1303.
  > doi: [10.1101/gr.107524.110](https://doi.org/10.1101/gr.107524.110).
  > <https://gatk.broadinstitute.org/> · Picard: <https://broadinstitute.github.io/picard/>

## Variant calling

- **GATK4 HaplotypeCaller** — germline SNV/indel calling, default caller (`modules/call/haplotypecaller.nf`)

  > Poplin R, Ruano-Rubio V, DePristo MA, et al. Scaling accurate genetic variant discovery to
  > tens of thousands of samples. bioRxiv. 2018:201178.
  > doi: [10.1101/201178](https://doi.org/10.1101/201178). <https://gatk.broadinstitute.org/>

- **DeepVariant** — deep-learning variant caller, selectable via `--caller deepvariant`
  (`modules/call/deepvariant.nf`)

  > Poplin R, Chang PC, Alexander D, et al. A universal SNP and small-indel variant caller using
  > deep neural networks. Nat Biotechnol. 2018;36(10):983-987.
  > doi: [10.1038/nbt.4235](https://doi.org/10.1038/nbt.4235).
  > <https://github.com/google/deepvariant>

## Analytical validation

- **hap.py** — benchmarking called variants against a truth set (`modules/validate/happy_benchmark.nf`)

  > Krusche P, Trigg L, Boutros PC, et al. Best practices for benchmarking germline small-variant
  > calls in human genomes. Nat Biotechnol. 2019;37(5):555-560.
  > doi: [10.1038/s41587-019-0054-x](https://doi.org/10.1038/s41587-019-0054-x).
  > <https://github.com/Illumina/hap.py>

- **Genome in a Bottle (GIAB)** — HG002/NA24385 reference material and high-confidence truth set
  (v4.2.1) used as the validation ground truth

  > Zook JM, Catoe D, McDaniel J, et al. Extensive sequencing of seven human genomes to
  > characterize benchmark reference materials. Sci Data. 2016;3:160025.
  > doi: [10.1038/sdata.2016.25](https://doi.org/10.1038/sdata.2016.25).
  > <https://www.nist.gov/programs-projects/genome-bottle>

## Standards interoperability (GA4GH)

- **GA4GH refget** — content-based reference sequence identifiers (`pipeline/bin/ga4gh_ids.py`;
  see [`docs/GA4GH-ALIGNMENT.md`](docs/GA4GH-ALIGNMENT.md))

  > refget API specification. GA4GH / htsspecs. <https://samtools.github.io/hts-specs/refget.html>
  >
  > Rehm HL, Page AJH, Smith L, et al. GA4GH: International policies and standards for data sharing
  > across genomic research and healthcare. Cell Genomics. 2021;1(2):100029.
  > doi: [10.1016/j.xgen.2021.100029](https://doi.org/10.1016/j.xgen.2021.100029).

- **GA4GH VRS** (Variation Representation Specification) — the `sha512t24u` computed-identifier
  scheme shared with refget (`pipeline/bin/ga4gh_ids.py`)

  > Wagner AH, Babb L, Alterovitz G, et al. The GA4GH Variation Representation Specification: A
  > computational framework for variation representation and federated identification.
  > Cell Genomics. 2021;1(2):100027.
  > doi: [10.1016/j.xgen.2021.100027](https://doi.org/10.1016/j.xgen.2021.100027).
  > <https://vrs.ga4gh.org/>

## Containers and packaging

- **Docker** — reproducible per-step execution environments. <https://www.docker.com/>
- **Biocontainers** — community-maintained bioinformatics container images used for most steps.

  > da Veiga Leprevost F, Grüning BA, Alves Aflitos S, et al. BioContainers: an open-source and
  > community-driven framework for software standardization. Bioinformatics. 2017;33(16):2580-2582.
  > doi: [10.1093/bioinformatics/btx192](https://doi.org/10.1093/bioinformatics/btx192).
  > <https://biocontainers.pro/>
