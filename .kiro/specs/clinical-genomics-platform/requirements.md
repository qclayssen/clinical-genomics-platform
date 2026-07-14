# Requirements Document

## Introduction

The Clinical Genomics Insight Platform is an end-to-end germline SNV variant-calling system demonstrating clinical bioinformatics patterns: raw WGS reads → QC → alignment → variant calling → truth-set validation → provenance-tracked results → ops dashboard → AI-drafted reporting. The platform is scoped to GIAB HG002 chr20 on GRCh38 and targets AWS free-tier compliance for all deployed resources. It evolves the existing scaffolded project by replacing AWS Batch/Fargate with Lambda + Step Functions orchestration, introducing DynamoDB as the primary data store, adding a RAG layer to the AI component, and integrating EventBridge-driven automation — all while maintaining NATA/ISO 15189 traceability patterns.

## Glossary

- **Pipeline**: The Nextflow DSL2 bioinformatics workflow that processes FASTQ reads through QC, alignment, variant calling, validation, and export stages
- **Step_Functions_Workflow**: The AWS Step Functions state machine that orchestrates the cloud execution of pipeline stages via Lambda functions
- **Lambda_Orchestrator**: AWS Lambda functions that coordinate pipeline execution, trigger ingestion, and produce AI reports
- **EventBridge_Rule**: AWS EventBridge rules that detect S3 object creation events and initiate the Step Functions workflow
- **Data_Lake**: The S3 bucket storing raw inputs, intermediate work files, and final results with versioning and encryption
- **DynamoDB_Store**: The AWS DynamoDB table(s) storing run metadata, QC metrics, provenance records, and audit trail entries in an append-only pattern
- **Metabase_Dashboard**: The Metabase BI layer presenting cohort QC trends, turnaround time, and failure rates
- **RAG_Reporter**: The Retrieval-Augmented Generation component that enriches AI-drafted reports with gene/variant annotation context from a local vector store
- **LoRA_Trainer**: The QLoRA fine-tuning component that adapts a small open-source LLM on genomics reporting data using free-tier compute
- **Guardrails_Engine**: The post-processing layer that enforces the review banner, provenance citation, and advice-phrase scrubbing on all AI output
- **Provenance_Stamp**: The structured metadata block (git commit, tool versions, reference versions, input checksums) attached to every pipeline result
- **Truth_Set**: The GIAB v4.2.1 high-confidence variant call set for HG002 chr20 used as the validation benchmark
- **CDK_App**: The AWS CDK TypeScript application that defines all cloud infrastructure as code
- **CI_Pipeline**: The GitHub Actions workflows that lint, test, synthesize, and validate all platform components on every push

## Requirements

### Requirement 1: Nextflow Pipeline Execution

**User Story:** As a bioinformatician, I want a modular Nextflow DSL2 pipeline that processes GIAB HG002 chr20 FASTQ reads through QC, alignment, variant calling, and validation, so that I can produce benchmarked variant calls with full provenance.

#### Acceptance Criteria

1. WHEN a sample sheet referencing paired-end FASTQ files for HG002 chr20 is provided, THE Pipeline SHALL execute stages in order: read trimming (fastp) → read QC (FastQC) → alignment (BWA-MEM2) → duplicate marking (MarkDuplicates) → variant calling (selected caller) → validation (hap.py) → structured export (JSON and Parquet) → aggregated QC report (MultiQC)
2. WHEN all pipeline stages complete successfully, THE Pipeline SHALL produce a MultiQC HTML report aggregating QC outputs from fastp, FastQC, MarkDuplicates, and hap.py
3. WHEN the validation stage completes, THE Pipeline SHALL calculate SNV precision, recall, and F1 against the Truth_Set and record a validation_pass flag set to true if SNV F1 is greater than or equal to 0.99
4. THE Pipeline SHALL embed a Provenance_Stamp in the output metrics.json containing git commit SHA, pipeline version, caller version, reference genome version, truth set version, and SHA-256 checksums of all input files
5. WHEN the Pipeline is invoked with the -stub flag, THE Pipeline SHALL validate the DAG structure by completing all process stubs with zero failures and without requiring bioinformatics tool containers or real sequencing data
6. WHEN any pipeline stage fails with a non-retryable exit code, THE Pipeline SHALL emit a structured error containing the failed process name, exit code, and stderr content; IF a stage fails with a retryable exit code (137, 143, 104, 134, or 139), THEN THE Pipeline SHALL retry the stage up to 2 times before emitting the structured error
7. THE Pipeline SHALL define one process per module file following nf-core conventions, with each process specifying a container directive
8. THE Pipeline SHALL support caller selection between HaplotypeCaller and DeepVariant via a caller parameter, defaulting to HaplotypeCaller when no selection is specified

### Requirement 2: AWS Lambda + Step Functions Orchestration

**User Story:** As a platform operator, I want the cloud execution orchestrated by Step Functions and Lambda instead of Batch/Fargate, so that the platform stays within AWS free-tier limits at demo scale.

#### Acceptance Criteria

1. THE CDK_App SHALL define a Step_Functions_Workflow state machine with states executing in order: trigger ingestion, run QC checks, run variant calling, validate results, export to Data_Lake, ingest metadata to DynamoDB_Store, and generate AI report
2. THE CDK_App SHALL define Lambda_Orchestrator functions (one per state machine state) with memory allocation not exceeding 512 MB and timeout not exceeding 15 minutes per invocation
3. WHEN a Step_Functions_Workflow execution completes successfully, THE Lambda_Orchestrator SHALL write a completion record to the DynamoDB_Store audit trail containing: `run_id`, action `WORKFLOW_COMPLETE`, execution start time, execution end time, and ISO 8601 completion timestamp
4. IF a Lambda_Orchestrator function fails, THEN THE Step_Functions_Workflow SHALL retry the failed step up to 2 times with exponential backoff (initial interval of 5 seconds, backoff rate of 2.0) before transitioning to a failure state
5. WHEN the Step_Functions_Workflow transitions to a failure state, THE Lambda_Orchestrator SHALL send a notification to the configured SNS topic and write a failure record to the DynamoDB_Store audit trail containing: `run_id`, action `WORKFLOW_FAILED`, failed state name, error cause, and ISO 8601 failure timestamp
6. THE CDK_App SHALL configure all Lambda functions with the least-privilege IAM roles scoped to only the resources each function accesses
7. THE CDK_App SHALL configure the Step_Functions_Workflow with a maximum concurrency of 1 execution at a time to remain within AWS free-tier state transition limits

### Requirement 3: EventBridge-Driven Automation

**User Story:** As a platform operator, I want new FASTQ uploads to S3 to automatically trigger the analysis workflow, so that samples are processed without manual intervention.

#### Acceptance Criteria

1. WHEN a new object is created in the Data_Lake under the prefix `raw/` (including nested sub-prefixes) with a `.fastq.gz` or `.fq.gz` extension (case-insensitive), THE EventBridge_Rule SHALL start a new Step_Functions_Workflow execution within 60 seconds of the object creation event
2. THE EventBridge_Rule SHALL pass the S3 bucket name, object key, and object size as input parameters to the Step_Functions_Workflow execution
3. IF an object created under `raw/` does not have a `.fastq.gz` or `.fq.gz` extension (case-insensitive), THEN THE EventBridge_Rule SHALL not start a Step_Functions_Workflow execution
4. THE CDK_App SHALL define the EventBridge_Rule with a retry policy of 3 attempts with exponential backoff and a dead-letter queue with a message retention period of 14 days for failed event deliveries
5. IF a new object version is created for an existing key in the Data_Lake under `raw/` due to versioning, THEN THE EventBridge_Rule SHALL start a new Step_Functions_Workflow execution (no deduplication of versioned uploads)
6. WHEN the dead-letter queue for the EventBridge_Rule contains 1 or more messages, THE CDK_App SHALL trigger a CloudWatch alarm to notify operators of failed event deliveries

### Requirement 4: S3 Data Lake

**User Story:** As a platform operator, I want an S3 data lake with versioning, encryption, and lifecycle policies, so that genomic data is stored securely with full audit trail and controlled costs.

#### Acceptance Criteria

1. THE Data_Lake SHALL enforce server-side encryption (SSE-S3) as the default encryption configuration, so that any object stored without an explicit encryption header is automatically encrypted at rest using AES-256
2. THE Data_Lake SHALL enforce TLS for all data in transit via a bucket policy containing an explicit Deny statement for any request where the condition `aws:SecureTransport` equals `false`
3. THE Data_Lake SHALL enable versioning so that every overwrite produces a new version and no prior version is removed by the overwrite operation
4. THE Data_Lake SHALL block all public access by enabling all four S3 Block Public Access settings: BlockPublicAcls, BlockPublicPolicy, IgnorePublicAcls, and RestrictPublicBuckets
5. THE Data_Lake SHALL apply a lifecycle rule that expires current-version objects under the `work/` prefix after 14 days
6. THE Data_Lake SHALL apply a lifecycle rule that transitions objects under the `raw/` prefix to Infrequent Access storage class after 30 days and to Glacier storage class after 180 days
7. THE CDK_App SHALL set the Data_Lake removal policy to RETAIN so that a `cdk destroy` operation does not delete the bucket or its contents

### Requirement 5: DynamoDB Metadata Store

**User Story:** As a platform developer, I want run metadata, QC metrics, provenance, and audit trail stored in DynamoDB on-demand mode, so that the platform uses the always-free tier with no idle cost.

#### Acceptance Criteria

1. THE CDK_App SHALL define a DynamoDB_Store table with on-demand (PAY_PER_REQUEST) billing mode and removal policy set to RETAIN so that `cdk destroy` does not delete stored data
2. THE DynamoDB_Store SHALL use a partition key of `run_id` (String) and a sort key of `record_type` (String) restricted to the values: `RUN`, `QC_METRICS`, `PROVENANCE`, `AUDIT`, and `CORRECTION`, to store all entities in a single-table design
3. THE DynamoDB_Store SHALL include a GSI with partition key `sample_id` and sort key `created_at` to support queries by sample across runs ordered by time
4. WHEN a new record is written to the DynamoDB_Store, THE Lambda_Orchestrator SHALL include a `created_at` attribute containing an ISO 8601 timestamp in UTC with seconds precision (e.g., `2024-01-15T09:30:00Z`)
5. THE DynamoDB_Store SHALL enforce append-only semantics: THE CDK_App SHALL deny `dynamodb:DeleteItem` and `dynamodb:UpdateItem` actions on the DynamoDB_Store for all Lambda_Orchestrator roles via IAM policy
6. THE DynamoDB_Store SHALL store provenance records (record_type `PROVENANCE`) containing: SHA-256 checksums of all input FASTQ files, pipeline version, caller tool and version, reference genome build and version, and truth set version
7. IF a correction is needed for a previous run, THEN THE Lambda_Orchestrator SHALL insert a new record with `record_type` set to `CORRECTION`, an `original_record_type` attribute identifying the corrected record type, a `correction_reason` attribute describing the reason, and the corrected field values, preserving the original record unchanged
8. THE CDK_App SHALL enable point-in-time recovery on the DynamoDB_Store table
9. IF a write to the DynamoDB_Store fails, THEN THE Lambda_Orchestrator SHALL retry the write up to 3 times with exponential backoff and, if all retries fail, SHALL publish an error event to the CloudWatch alarm topic and transition the Step_Functions_Workflow to a failure state

### Requirement 6: Observability and Monitoring

**User Story:** As a platform operator, I want CloudWatch logs, metrics, and alarms for all Lambda functions and Step Functions executions, so that I can detect and diagnose failures quickly.

#### Acceptance Criteria

1. THE CDK_App SHALL configure all Lambda_Orchestrator functions to emit structured JSON logs to CloudWatch Logs with a retention period of 30 days, where each log entry includes at minimum: timestamp, log level, run_id, function name, and message fields
2. THE CDK_App SHALL define a CloudWatch alarm that triggers when the Step_Functions_Workflow `ExecutionsFailed` metric is greater than or equal to 1 within a 1-minute evaluation period
3. THE CDK_App SHALL define a CloudWatch alarm that triggers when any Lambda_Orchestrator function error rate exceeds 5% over a 5-minute evaluation period with a minimum of 10 invocations in that period, treating missing data as `notBreaching`
4. THE CDK_App SHALL configure all CloudWatch alarms to publish a notification to an SNS topic when entering ALARM state
5. WHEN a Step_Functions_Workflow execution exceeds 30 minutes of elapsed time, THE CDK_App SHALL trigger a CloudWatch alarm on the `ExecutionTime` metric

### Requirement 7: IAM Least-Privilege

**User Story:** As a security reviewer, I want all IAM policies scoped to minimum necessary permissions, so that the platform follows security best practices required by accreditation frameworks.

#### Acceptance Criteria

1. THE CDK_App SHALL define a separate IAM role for each Lambda_Orchestrator function with permissions scoped to only the specific S3 prefixes, DynamoDB actions, and Step Functions actions that function requires
2. THE CDK_App SHALL attach an explicit deny policy to all Lambda_Orchestrator roles blocking `dynamodb:DeleteItem`, `dynamodb:UpdateItem`, and `dynamodb:DeleteTable` actions on the DynamoDB_Store table to enforce append-only behavior at the IAM level
3. THE CDK_App SHALL attach an explicit deny policy to all Lambda_Orchestrator roles blocking `s3:DeleteObject` and `s3:DeleteObjectVersion` on the `raw/*` and `results/*` prefixes of the Data_Lake bucket, with no exception for any Lambda role
4. THE CDK_App SHALL pass CDK guardrail tests asserting that no IAM policy attached to a Lambda_Orchestrator role grants `*` as a resource ARN or includes any `iam:*` action
5. THE CDK_App SHALL ensure that no Lambda_Orchestrator role includes any `iam:CreatePolicy`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, or `sts:AssumeRole` action to prevent privilege escalation

### Requirement 8: Metabase Dashboard

**User Story:** As a lab manager, I want a Metabase dashboard showing cohort QC trends, turnaround times, and failure rates, so that I can monitor operational performance at a glance.

#### Acceptance Criteria

1. THE Metabase_Dashboard SHALL display a time-series chart of mean SNV F1 scores grouped by pipeline version and variant caller, with pipeline version on the x-axis and F1 score (range 0.0 to 1.0) on the y-axis
2. THE Metabase_Dashboard SHALL display a turnaround time chart showing elapsed minutes from run start to export completion for the 20 most recent runs, ordered by start time descending
3. THE Metabase_Dashboard SHALL display a pass/fail ratio for validation results over a configurable time window selectable from 7, 30, or 90 days, defaulting to 30 days
4. THE Metabase_Dashboard SHALL display duplication rate trends as a bar chart showing percent duplication (0.0 to 100.0%) per sample, ordered by duplication rate descending
5. WHEN a run record is ingested into the DynamoDB_Store, THE Metabase_Dashboard SHALL reflect that run within 5 minutes
6. THE Metabase_Dashboard SHALL run on a local Docker container connecting to the data store via the docker-compose service configuration
7. IF no run data exists for the selected time window, THEN THE Metabase_Dashboard SHALL display an empty-state message indicating no data is available for the selected period

### Requirement 9: RAG-Augmented AI Reporting

**User Story:** As a bioinformatician, I want AI-drafted reports enriched with gene and variant annotation context from a local knowledge base, so that reports include relevant clinical context without requiring paid cloud AI services.

#### Acceptance Criteria

1. THE RAG_Reporter SHALL maintain a local vector store (FAISS or ChromaDB) indexed over gene annotations, variant significance databases, and mutational signature descriptions, containing at minimum one entry per gene present in the platform's target region
2. WHEN generating a report for a sample, THE RAG_Reporter SHALL retrieve up to 5 context passages (each no longer than 512 tokens) from the vector store, ranked by cosine similarity to the sample's variant and metric content, including only passages with a similarity score ≥ 0.70
3. IF fewer than 5 passages meet the similarity threshold of 0.70, THEN THE RAG_Reporter SHALL proceed with however many passages qualified (including zero) and generate the report without error
4. THE RAG_Reporter SHALL pass retrieved context passages along with the structured metrics.json to a local open-source LLM (via Ollama or HuggingFace transformers) for report generation, producing an output between 120 and 300 words
5. THE RAG_Reporter SHALL run entirely on local compute with no calls to paid cloud AI services (no Bedrock, no paid SageMaker endpoints)
6. WHEN the RAG_Reporter generates a report, THE Guardrails_Engine SHALL enforce the `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner, a provenance citation line, and scrub any phrasing matching clinical recommendation patterns (e.g., "recommend", "diagnose", "treat with")
7. IF the local LLM fails to respond within 120 seconds or raises any runtime error (model file missing, out-of-memory, or dependency failure), THEN THE RAG_Reporter SHALL fall back to the deterministic offline template renderer and log a warning indicating the failure reason

### Requirement 10: LoRA Fine-Tuning on Free Compute

**User Story:** As an ML engineer, I want to fine-tune a small open-source LLM on genomics reporting data using QLoRA on free-tier compute, so that report quality improves without incurring cloud AI costs.

#### Acceptance Criteria

1. THE LoRA_Trainer SHALL fine-tune a model with 3B parameters or fewer using 4-bit QLoRA adapters, with peak GPU memory usage not exceeding 12 GB VRAM
2. THE LoRA_Trainer SHALL train on paired data consisting of structured metrics.json inputs and corresponding report outputs in JSONL format, with a minimum of 10 training examples
3. THE LoRA_Trainer SHALL produce adapter weights in PEFT-compatible format that can be loaded at inference time by the RAG_Reporter using PeftModel.from_pretrained without reloading the full base model
4. THE LoRA_Trainer SHALL include a CPU-only smoke test that completes in under 5 minutes, running the full training loop end-to-end on at least 5 sample pairs, producing a saved adapter, and generating at least one token from the resulting model
5. THE LoRA_Trainer SHALL execute on free-tier compute platforms (Google Colab, Kaggle Notebooks, SageMaker Studio Lab, or local CPU/GPU) with no paid AWS services
6. WHEN a new adapter checkpoint is produced, THE LoRA_Trainer SHALL record in a model card: learning rate, batch size, gradient accumulation steps, number of epochs, LoRA rank, LoRA alpha, dataset version, base model identifier, and final training loss
7. IF training fails or is interrupted before completion, THEN THE LoRA_Trainer SHALL exit with a non-zero status code and SHALL NOT overwrite any previously saved adapter checkpoint

### Requirement 11: Provenance and Audit Trail

**User Story:** As a quality assurance reviewer, I want every pipeline result to carry a full provenance stamp and every system action to be recorded in an append-only audit trail, so that the platform demonstrates ISO 15189 traceability patterns.

#### Acceptance Criteria

1. THE Pipeline SHALL generate a Provenance_Stamp for every run containing: git commit SHA (40-character hex string), pipeline version (semver), caller tool name and version, reference genome build identifier and version, truth set version, and SHA-256 checksums of all input FASTQ files, written as a JSON object within the output metrics.json
2. WHEN a pipeline run completes, THE Lambda_Orchestrator SHALL write an audit trail entry to the DynamoDB_Store within 30 seconds containing: action `PIPELINE_COMPLETE`, the run_id, and a timestamp in ISO 8601 UTC format
3. WHEN an AI report is generated, THE Lambda_Orchestrator SHALL write an audit trail entry to the DynamoDB_Store containing: action `REPORT_DRAFTED`, the run_id, model version, adapter version (or `null` if zero-shot fallback was used), and a timestamp in ISO 8601 UTC format
4. THE DynamoDB_Store SHALL reject all attempts to update or delete existing audit trail entries via IAM deny policies on `dynamodb:UpdateItem` and `dynamodb:DeleteItem` actions, returning an Access Denied error to the caller
5. WHEN a validation result shows SNV F1 strictly below 0.99, THE Pipeline SHALL mark the run as `validation_pass: false` and THE Lambda_Orchestrator SHALL write an audit entry with action `VALIDATION_FAILED`, the run_id, and the observed F1 score to the DynamoDB_Store
6. IF the Lambda_Orchestrator fails to write an audit trail entry to the DynamoDB_Store after 3 retry attempts, THEN THE Lambda_Orchestrator SHALL publish a CloudWatch alarm notification and the Step_Functions_Workflow SHALL transition to a failure state without discarding the pending audit data from the event payload

### Requirement 12: Docker Containerization

**User Story:** As a DevOps engineer, I want every pipeline stage and platform component containerized with pinned images, so that execution is reproducible across environments.

#### Acceptance Criteria

1. THE Pipeline SHALL specify a container directive for every Nextflow process referencing a pinned Docker image by sha256 digest for images sourced from registries that support Content Trust, and by exact version tag for images from registries that do not publish digests
2. THE Pipeline SHALL use Biocontainers registry images (quay.io/biocontainers) for standard bioinformatics tools (BWA-MEM2, GATK, hap.py, samtools, bcftools, fastp, FastQC, MultiQC, DeepVariant)
3. THE CDK_App SHALL package Lambda_Orchestrator functions as container images built from a Dockerfile that is tracked in version control and that pins its base image by sha256 digest
4. THE Metabase_Dashboard SHALL run in a Docker container defined by a docker-compose service with the image version pinned to an exact release tag (e.g., metabase/metabase:vX.Y.Z)
5. THE RAG_Reporter SHALL run in a single Docker container with the vector store, LLM runtime, and inference code included in the image
6. WHEN a Dockerfile or docker-compose file defines a dependency installation step, THE Platform SHALL pin every dependency to an exact version (package manager lock file or explicit version specifier) so that repeated builds produce identical installed software

### Requirement 13: CI/CD via GitHub Actions

**User Story:** As a developer, I want GitHub Actions workflows that lint, test, and validate all platform components on every push, so that regressions are caught before merge.

#### Acceptance Criteria

1. WHEN a push or pull request affects pipeline files, THE CI_Pipeline SHALL run Nextflow configuration validation and nf-core linting on the pipeline, completing within 10 minutes
2. WHEN a push or pull request affects pipeline files, THE CI_Pipeline SHALL execute the pipeline stub test (`nextflow run -stub`) to validate that all processes are reachable and the DAG resolves without errors, completing within 10 minutes
3. WHEN a push or pull request affects infrastructure files, THE CI_Pipeline SHALL run TypeScript type-checking (`tsc --noEmit`) and `cdk synth --all` to validate CDK templates compile without errors, completing within 10 minutes
4. WHEN a push or pull request affects pipeline, ai-report, or db files, THE CI_Pipeline SHALL run the Python unit test suite (`pytest tests/`) and the AI guardrail validation to verify provenance metadata and clinician-review banner are present in generated reports, completing within 10 minutes
5. WHEN a push or pull request affects ai-report files, THE CI_Pipeline SHALL run the ML CPU smoke test (`train_smoke.py`) to verify the LoRA fine-tuning loop completes at least 1 training step without error, completing within 15 minutes
6. IF any CI_Pipeline job fails, THEN THE CI_Pipeline SHALL mark the corresponding GitHub status check as failed, preventing the pull request from merging via branch protection required status checks
7. THE CI_Pipeline SHALL request only read-level repository permissions (contents: read) for all workflow jobs

### Requirement 14: Cost Guardrails

**User Story:** As the project owner, I want infrastructure guardrail tests that verify all AWS resources stay within free-tier limits at demo scale, so that I never incur unexpected charges.

#### Acceptance Criteria

1. THE CDK_App SHALL configure DynamoDB tables in on-demand mode (always-free tier: 25 WCU / 25 RCU equivalent, 25 GB storage)
2. THE CDK_App SHALL configure all Lambda functions with memory not exceeding 512 MB and timeout not exceeding 15 minutes per invocation (free tier: 1,000,000 requests + 400,000 GB-seconds per month)
3. THE CDK_App SHALL NOT provision AWS Batch, Fargate, NAT Gateways, or RDS instances
4. THE CDK_App SHALL NOT provision Bedrock endpoints, SageMaker endpoints, Comprehend endpoints, Rekognition resources, or Kendra indexes
5. THE CDK_App SHALL include CDK guardrail tests that assert the synthesized CloudFormation template contains zero resources of types `AWS::Batch::*`, `AWS::ECS::Service`, `AWS::EC2::NatGateway`, `AWS::RDS::*`, `AWS::Bedrock::*`, `AWS::SageMaker::Endpoint`, `AWS::Kendra::*`, and `AWS::Comprehend::*`
6. THE CDK_App SHALL define a CloudWatch billing alarm on the `EstimatedCharges` metric in the `AWS/Billing` namespace that transitions to ALARM state when the total exceeds $1 USD, evaluated over a single period of 6 hours, and publishes a notification to an SNS topic
7. THE CDK_App SHALL NOT provision more than 4,000 Step Functions state transitions per month at demo scale (free tier: 4,000 state transitions per month)

### Requirement 15: Production Migration Path Documentation

**User Story:** As a hiring manager reviewing this project, I want documentation describing how each free-tier component would be replaced by production-grade AWS services, so that I can assess the candidate's understanding of production architecture.

#### Acceptance Criteria

1. THE CDK_App documentation SHALL describe AWS HealthOmics as the production migration path for pipeline execution, including how the Nextflow workflow would map to HealthOmics private workflows
2. THE CDK_App documentation SHALL describe Amazon Aurora Serverless as the production replacement for DynamoDB when relational query patterns are needed
3. THE CDK_App documentation SHALL describe Amazon Bedrock with guardrails as the production replacement for the local RAG_Reporter
4. THE CDK_App documentation SHALL describe AWS SageMaker as the production fine-tuning platform replacing local/Colab LoRA training
5. THE CDK_App documentation SHALL describe the cost and operational trade-offs for each production alternative versus the free-tier implementation
