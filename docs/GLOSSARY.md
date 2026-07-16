# Glossary — every term in this project, explained simply

Plain-language definitions for every piece of jargon used in this repo. Grouped by topic.
Each entry: **what it is** in one line, and often an everyday **analogy**.

If you're brand new, read [BEGINNERS-GUIDE.md](BEGINNERS-GUIDE.md) first — it uses these
terms in a story.

---

## 1. DNA, sequencing & genomics

**DNA**
The molecule carrying genetic instructions, written in a 4-letter alphabet: `A`, `C`, `G`,
`T`. Reading it is the starting point of everything here.

**Genome**
The complete set of DNA in one organism. The human genome is ~3 billion letters long.
*Analogy:* the entire instruction manual for building and running a person.

**Sequencing**
The lab process of reading the letters of DNA using a machine (a "sequencer").
*Analogy:* scanning a book into text — except the scanner shreds the book first.

**Read**
One short fragment of DNA letters produced by the sequencer (typically 100–300 letters).
Millions are produced per sample. *Analogy:* a single shredded strip from the scanned book.

**WGS (Whole-Genome Sequencing)**
Sequencing *all* of someone's DNA, not just selected parts. This project uses WGS data.

**Reference genome / reference build (e.g. GRCh38)**
A standard, agreed-upon "template" human genome that everyone compares against. **GRCh38**
is the current standard version ("build"). *Analogy:* the master copy of the instruction
manual, so you can say "this person's page 400 differs from the master."

**chr20 (chromosome 20)**
DNA is organised into 23 pairs of **chromosomes**. This project only processes chromosome
20 — a deliberate slice to keep data small and runnable on a laptop. *Analogy:* proving your
method works on one chapter before doing the whole book.

**Variant**
A spot where a sample's DNA differs from the reference genome. Finding these is the whole
point. *Analogy:* a typo (or intentional edit) compared to the master manual.

**SNV / SNP (Single-Nucleotide Variant / Polymorphism)**
The simplest kind of variant: a single letter changed (e.g. reference has `A`, sample has
`G`). This project focuses on SNVs.

**INDEL**
A variant where letters are **in**serted or **del**eted. Reported here for information, but
not the main focus.

**Germline**
Variants you're **born with** (inherited), present in every cell — as opposed to *somatic*
variants that a tumour acquires later. This project does **germline** calling.

**Clonotype / immune repertoire** *(mentioned as a possible future extension)*
A different kind of analysis: cataloguing the diversity of immune-system cells rather than
DNA variants. Not built here, but the platform is designed so it could be added.

**Ti/Tv (Transition/Transversion ratio)**
A sanity-check number about the *types* of DNA changes found. A value in the expected range
suggests the variant calls are biologically believable, not random noise.

**Depth / coverage**
How many times, on average, each position of DNA was read. Higher depth = more confidence.
*Analogy:* re-reading the same sentence 30 times so you're sure of every word.

---

## 2. File formats (the data as it flows through)

**FASTQ**
The raw input file: millions of reads plus a quality score for each letter. *The shredded,
unassembled book.*

**FASTA (`.fa`)**
A simpler format storing a reference sequence (just letters, no quality scores). The
reference genome is a FASTA file.

**BAM**
The reads *after* alignment — each read now positioned against the reference. *The shredded
strips taped back onto their correct pages.* (A **SAM** is the same thing in plain text;
BAM is the compressed version.)

**VCF (Variant Call Format)**
The list of variants found — the key scientific output. *The list of every typo versus the
master manual, with its exact location.*

**JSON**
A general, human-readable way to store structured data as labelled fields. This project
bundles each sample's key metrics into a JSON file. *Analogy:* a filled-in form with labelled
boxes.

**Parquet**
A compact, table-shaped file format that dashboards and analytics tools read efficiently.
Same data as the JSON, packed for fast querying.

**BED**
A simple file listing regions of the genome ("from position X to Y"). Used here to say
"only grade yourself within these high-confidence regions."

---

## 3. The pipeline tools (the assembly line)

**Pipeline**
The whole automated sequence of steps from raw data to final result. *The factory assembly
line.*

**Nextflow**
The software that *orchestrates* the pipeline — runs each step in the right order, in
parallel where possible, and restarts cleanly on failure. *The factory foreman.*

**DSL2**
The modern style/syntax of writing Nextflow pipelines in reusable **modules**. Just means
"the current, modular way to write Nextflow."

**nf-core**
A community's set of best-practice standards for writing Nextflow pipelines. "nf-core style"
= "follows the conventions professionals expect."

**Module**
One reusable step of the pipeline in its own file (e.g. the "align" step). *One station on
the assembly line.*

**FastQC / fastp**
Tools that inspect and clean the raw reads (step 2). fastp also trims junk off the ends.

**MultiQC**
A tool that gathers all the little quality reports into one combined, browsable HTML report.

**BWA-MEM2**
The **aligner** — works out where each read belongs on the reference genome (step 3).

**MarkDuplicates**
Flags accidental duplicate reads so they don't skew results (step 4). Part of a toolkit
called **Picard/GATK**.

**GATK**
The "Genome Analysis Toolkit" — an industry-standard bundle of genomics tools. We use its
**HaplotypeCaller** to find variants.

**HaplotypeCaller**
GATK's variant-calling tool (step 5). One of the two callers this project supports.

**DeepVariant**
Google's variant caller that uses a neural network (AI) to call variants. The project's
*second* caller option, so you can compare the two.

**hap.py** ("happy")
The tool that **grades** our variant calls against the truth set and computes precision,
recall, and F1 (step 6). *The exam marker.*

**xcmp**
The comparison "engine" hap.py uses under the hood to match up variants fairly — hap.py's
original, self-contained engine. This is what the platform actually runs (see ADR-0015).

**vcfeval**
An alternative, more sophisticated comparison engine for hap.py. Not used here: it needs an
external tool (`rtg-tools`) that isn't in the pinned `hap.py` container (ADR-0015).

**seqtk**
A small utility for subsampling FASTQ files (taking a random slice) to make test data
smaller.

**bcftools / samtools**
Swiss-army-knife command-line tools for manipulating VCF (bcftools) and BAM/FASTA
(samtools) files.

---

## 4. The "answer key" — reference/truth data

**Truth set / benchmark**
A sample whose *correct* variant list is already known and published, used to grade your
pipeline. *The answer key at the back of the textbook.*

**GIAB (Genome in a Bottle)**
A public project (run by the US standards agency, NIST) that publishes gold-standard truth
sets. Free, well-known, and exactly what a serious validation uses.

**HG002 / NA24385**
The specific well-characterised person's sample this project benchmarks against (nicknames
for the same reference individual). Public and consented for exactly this use.

**High-confidence regions**
The parts of the genome where the truth set is *certain* it's correct. We only grade
ourselves there, and honestly declare the rest "out of scope." *Only marking the exam
questions the answer key is sure about.*

---

## 5. Accuracy metrics (the score)

**Precision**
Of the variants we *reported*, what fraction were actually real? High precision = few false
alarms. *If you flag 100 typos and 99 are genuine, precision is 99%.*

**Recall (sensitivity)**
Of the variants that *truly exist*, what fraction did we *catch*? High recall = few misses.
*If there were 100 real typos and you found 97, recall is 97%.*

**F1 score**
A single number balancing precision and recall (their "harmonic mean"). Used as the overall
pass/fail measure. *One combined grade instead of two.*

**Acceptance criterion / threshold**
The pre-agreed bar a run must clear to "pass" (here: **F1 ≥ 0.99**). Deciding this *before*
running is a hallmark of proper validation.

**validation_pass**
The true/false flag recorded for each run saying whether it cleared the threshold.

---

## 6. The database

**Database**
Organised storage you can query. *A very smart filing cabinet.*

**PostgreSQL (Postgres)**
The specific, widely-used, free database this project uses.

**Schema**
The blueprint defining what tables exist and what columns they have. *The labelled layout of
the filing cabinet's drawers.*

**Table / row / column**
A table is a grid; each **row** is one record (e.g. one pipeline run); each **column** is one
field (e.g. "precision").

**Insert-only / immutable**
Our design choice: you can **add** records but never edit or delete existing ones.
Corrections are added as *new* records. *Like a ledger written in permanent ink.* This
mirrors medical-record rules.

**Provenance**
The full "where did this come from" record for a result: software version, reference used,
input fingerprints, timestamps. *The manufacturing/paper trail for a result.*

**Checksum / SHA-256 / hash**
A short digital fingerprint of a file. If even one letter of the file changes, the
fingerprint changes completely — so it proves a file is exactly what it was. *A tamper-evident
seal.*

**Audit log / audit trail**
An append-only record of every action taken ("ingested sample X at time Y"). *The security
camera footage of the data.*

**Migration**
A versioned script that sets up or updates the database structure in a controlled, repeatable
way. *A dated blueprint revision.*

**View**
A saved, reusable query that presents data in a convenient shape (we use one to feed the
dashboard). *A pre-set report template.*

**Trigger**
Database logic that runs automatically on an event. We use triggers to *block* any attempt
to edit/delete the immutable tables. *An automatic alarm on the ledger.*

**JSONB**
Postgres's efficient way of storing JSON data inside a database column.

---

## 7. The dashboard

**Metabase**
Free software that connects to the database and turns it into charts and dashboards without
writing code each time. *The business-intelligence screen for non-programmers.*

**BI (Business Intelligence)**
General term for "turning data into charts/reports that help people make decisions."

**Dashboard**
A single screen showing the key charts at a glance. *A car's dashboard, for lab operations.*

**Turnaround time**
How long a sample took from start to finish — a key operational metric for a lab.

---

## 8. AI / machine-learning terms

**LLM (Large Language Model)**
An AI trained on huge amounts of text that can read and write human language (the same
family of tech as ChatGPT). Here it drafts the plain-language summary.

**Model**
The trained AI itself — the file(s) containing everything it "learned." *A very elaborate
auto-complete.*

**Open model (e.g. Llama, Phi)**
An LLM whose weights are publicly available so you can run and customise it yourself, rather
than only calling someone's paid service.

**Fine-tuning**
Taking a general pre-trained model and training it a bit more on *your* specific examples so
it gets good at *your* task. *Sending a capable generalist on a short specialist course.*

**LoRA / QLoRA**
Efficient fine-tuning methods that adjust only a small add-on ("adapter") instead of the
whole model, so it's cheap enough to do on a single rented GPU. **QLoRA** is the
memory-saving ("quantized") version. *Teaching new tricks by adding sticky notes rather than
rewriting the whole textbook.*

**Adapter / checkpoint**
The small file produced by LoRA fine-tuning that holds the new specialist knowledge; loaded
on top of the base model at run time.

**Prompt**
The instructions you give the model. *The exact wording of the request.*

**Zero-shot**
Asking the model to do a task using only a prompt, with no fine-tuning. This project's
**fallback** path. *Asking a smart generalist to do it cold.*

**Inference**
Actually *using* a trained model to produce output (as opposed to training it). Our
`infer.py` does inference.

**GPU**
A specialised processor that AI training/running needs. *A very fast, very parallel engine.*

**Guardrails**
Hard rules the AI output must obey — here, always stamping "REQUIRES CLINICIAN REVIEW",
citing source fields, and never giving medical advice. Enforced in code so the model *can't*
skip them. *Guard rails on a mountain road.*

**Hallucination**
When an LLM confidently makes something up. Our guardrails + "human signs off" design exist
precisely to contain this risk.

**Dependency-free**
Code that runs with no special extra software installed. This project's metrics parser and
an "offline" version of the report writer are dependency-free, so they run and are tested
anywhere with basic Python — no GPU or AI libraries needed.

---

## 9. Cloud & AWS (running it at scale)

**Cloud**
Renting someone else's computers over the internet instead of owning them. *Renting a
workshop by the hour instead of building one.*

**AWS (Amazon Web Services)**
The most common cloud provider. This project deploys to AWS.

**IaC (Infrastructure as Code)**
Describing your cloud setup in code files, so it's repeatable, reviewable, and version-
controlled — instead of clicking buttons in a web console. *A written recipe instead of
improvising each time.*

**AWS CDK (Cloud Development Kit)**
Amazon's tool for writing Infrastructure as Code in a normal programming language
(TypeScript here). Our `infra/` folder.

**Stack**
One deployable bundle of related cloud resources defined by the CDK (we have four: data
lake, compute, IAM, observability).

**S3 (Simple Storage Service)**
AWS's file storage. Our **data lake** lives here.

**Data lake**
A central storage area holding all the raw and processed data. *One big, organised
warehouse.*

**Versioned storage / object lock**
S3 settings so files are never silently overwritten or deleted before a retention period —
supporting the audit trail. *Every version kept; nothing shreddable on a whim.*

**AWS Batch**
A service that runs lots of computing jobs on rented machines and shuts them down when done —
ideal for pipelines. *Hiring temp workers only for the shift you need.*

**Fargate**
A way to run those jobs without managing any servers yourself. *Temp workers who bring their
own desk.*

**Spot (instances)**
Cheaper cloud computing using AWS's spare capacity. Cost-saving for non-urgent work.

**VPC (Virtual Private Cloud)**
Your own private, walled-off network inside AWS where the jobs run, off the public internet.
*A fenced compound.*

**IAM (Identity and Access Management)**
AWS's permissions system: who/what is allowed to do what. *The building's keycard system.*

**Least privilege**
The security principle of granting the *minimum* permissions needed and no more. Our pipeline
jobs can read inputs but are explicitly forbidden from deleting them. *Give the cleaner a key
to the office, not the safe.*

**Role**
A named bundle of permissions that a service can temporarily assume. *A job title with a
defined set of keys.*

**CloudWatch**
AWS's logging and monitoring service — collects logs and raises alarms. *The building's
CCTV + smoke alarms.*

**Alarm**
An automatic alert when something crosses a threshold (e.g. a job failed).

**CloudTrail**
AWS's record of *who did what* in your account — another audit-trail layer.

**cdk synth / cdk deploy**
`synth` = turn the CDK code into the raw cloud template (a dry run / preview). `deploy` =
actually create the resources. *Print the blueprint vs. actually build.*

**Region**
The geographic location of the AWS data centres you're using (e.g. `ap-southeast-2` =
Sydney).

---

## 10. Containers, DevOps & general software

**Docker**
Software that packages a tool with *everything it needs* into a sealed "container" that runs
identically on any machine. Solves "but it works on my computer." *A shipping container:
same box, any ship.*

**Container**
One running, isolated instance of a Docker image. *One sealed box, opened and in use.*

**Image**
The saved template a container is created from. *The mould the box is stamped from.*

**Dockerfile**
The recipe describing how to build an image.

**Pinned / by digest**
Locking to an *exact* version of an image (by its unique fingerprint) so it can never change
under you. Important for reproducibility and audits. *Ordering "this exact serial number,"
not "the latest model."*

**Biocontainers**
A public collection of ready-made Docker images for bioinformatics tools.

**docker-compose**
A tool to start several containers together (we use it to launch Postgres + Metabase at
once). *One switch that powers up the whole demo rig.*

**Git**
Software that tracks every change to your code and its history. *An infinite undo button +
logbook for a project.*

**Repository (repo)**
A project tracked by Git. This whole folder is one.

**Commit**
One saved snapshot of changes in Git, with a message describing them. *A labelled save
point.*

**CI (Continuous Integration)**
Automation that checks your code every time you change it (runs tests, linting, etc.). *A
robot reviewer that never sleeps.*

**GitHub Actions**
GitHub's built-in CI system. Our `.github/workflows/` files define it.

**Lint / linting**
Automated checking of code for style and obvious mistakes. *A spell-checker for code.*

**Test / unit test**
Code that automatically checks other code does the right thing. Ours verify the metrics
parser and AI guardrails. *A quality-control probe on the assembly line.*

**pytest / jest**
The test-running tools used here — **pytest** for Python, **jest** for the TypeScript infra
code.

**Stub / stub run**
A fake, instant run of the pipeline that checks the *structure* is valid without doing the
heavy computation. *A fire drill: full walkthrough, no actual fire.*

**TypeScript**
The programming language the cloud-infrastructure code is written in (a stricter version of
JavaScript).

**Python**
The programming language the helper scripts and AI code are written in.

**SQL (Structured Query Language)**
The language for asking a database questions ("give me all failed runs"). *How you talk to
the filing cabinet.*

**YAML / CSV**
Simple text file formats: **YAML** for configuration (the CI files), **CSV** for spreadsheet-
like tables (the sample sheet).

**Sample sheet**
The input list telling the pipeline which files belong to which sample. *The order form.*

---

## 11. Clinical / accreditation context

**Clinical bioinformatics**
Using computational biology specifically in a healthcare/diagnostic setting, where
correctness and traceability are regulated.

**ISO 15189**
The international quality standard for medical laboratories. This project *imitates its
patterns* (validation, provenance, audit) to show familiarity — it is **not** certified.

**NATA**
Australia's accreditation body that audits labs against standards like ISO 15189.

**Accreditation**
Official certification that a lab meets a quality standard. Requires exactly the traceability
and validation this project demonstrates.

**Validation (analytical validation)**
Formally proving a test performs well enough for its purpose — here, benchmarking against
GIAB and reporting precision/recall. *Proving the ruler measures accurately before you trust
its measurements.*

**Provenance / traceability**
(See §6.) The ability to reconstruct exactly how any result was produced. A core
accreditation requirement.

**Change control**
Managing changes carefully: any change to the method triggers re-validation before release.
*You don't quietly swap a part on a certified machine — you re-test and re-certify.*

**SOP (Standard Operating Procedure)**
A formal written document describing exactly how to perform a procedure, with acceptance
criteria and deviation handling. See [SOP-run-pipeline.md](SOP-run-pipeline.md).

**Human-in-the-loop**
A design where AI assists but a qualified human makes the final decision. Our AI *drafts*;
a clinician *signs*.
