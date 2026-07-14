# Implementation Plan: Clinical Genomics Platform — Serverless Evolution

## Overview

This plan evolves the existing scaffolded platform from Batch/Fargate compute to a serverless Lambda + Step Functions architecture, adds DynamoDB as the primary metadata store, implements a local RAG layer for AI reporting, and ensures all infrastructure remains within AWS free-tier limits. Tasks are ordered for incremental demoability: infrastructure first, then Lambda handlers, then AI/RAG, then property-based tests, then CI updates and documentation.

**Languages:** TypeScript (CDK infrastructure), Python (Lambda handlers, RAG layer, property tests)

## Tasks

- [x] 1. Create metadata-stack.ts — DynamoDB single-table design
  - [x] 1.1 Create `infra/lib/metadata-stack.ts` with DynamoDB table definition
    - Define table `cgp-metadata` with PK `run_id` (String), SK `record_type` (String)
    - Set billing mode to PAY_PER_REQUEST (on-demand)
    - Enable point-in-time recovery (PITR)
    - Set removal policy to RETAIN
    - Add GSI `sample_id-created_at-index` (PK: `sample_id`, SK: `created_at`)
    - Export the `metadataTable` as a public property for cross-stack references
    - _Requirements: 5.1, 5.2, 5.3, 5.8_

- [x] 2. Replace iam-stack.ts — per-Lambda least-privilege roles
  - [x] 2.1 Rewrite `infra/lib/iam-stack.ts` with 7 per-Lambda IAM roles
    - Remove `batchJobRole` and `batchExecutionRole`
    - Create roles: `ingestionTriggerRole`, `qcOrchestratorRole`, `variantCallingRole`, `validationCheckerRole`, `exportHandlerRole`, `metadataIngestorRole`, `reportGeneratorRole`
    - Each role assumed by `lambda.amazonaws.com` service principal
    - Grant CloudWatch Logs permissions (`CreateLogGroup`, `CreateLogStream`, `PutLogEvents`) to all roles
    - Scope S3 actions per-function (e.g. ingestion reads `raw/*`, export writes `results/*`)
    - Add explicit DENY for `dynamodb:DeleteItem`, `dynamodb:UpdateItem`, `dynamodb:DeleteTable` on the metadata table for all roles
    - Add explicit DENY for `s3:DeleteObject`, `s3:DeleteObjectVersion` on `raw/*` and `results/*` for all roles
    - Ensure no role grants `*` as resource ARN or includes any `iam:*` action
    - Block `iam:CreatePolicy`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `sts:AssumeRole` on all roles
    - Accept `dataLakeBucket` and `metadataTable` as stack props
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 5.5_

- [x] 3. Replace compute-stack with orchestration-stack.ts
  - [x] 3.1 Create `infra/lib/orchestration-stack.ts` with Step Functions + Lambda + EventBridge
    - Remove `compute-stack.ts` (or archive it)
    - Define 7 Lambda functions (Python runtime, container image packaging) with memory ≤512 MB, timeout ≤15 min
    - Define Step Functions state machine with states: TriggerIngestion → RunQC → RunVariantCalling → ValidateResults → ExportToS3 → IngestMetadata → GenerateReport → WorkflowComplete
    - Add HandleFailure catch state with SNS notification
    - Configure retry on each state: MaxAttempts=2, IntervalSeconds=5, BackoffRate=2.0
    - Set state machine `maxConcurrency: 1`
    - Define EventBridge rule matching S3 PutObject on `raw/` prefix with `.fastq.gz` suffix
    - Define SQS dead-letter queue (14-day retention) for failed EventBridge deliveries
    - Define SNS topic for failure notifications
    - Accept `dataLakeBucket`, `metadataTable`, and `lambdaRoles` as stack props
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.4, 3.5_

  - [x] 3.2 Add EventBridge notification to `data-lake-stack.ts`
    - Add `this.bucket.enableEventBridgeNotification()` to the existing DataLakeStack
    - Preserve all existing bucket configuration unchanged
    - _Requirements: 3.1, 4.1–4.7_

- [x] 4. Evolve observability-stack.ts — Lambda/SFN metrics
  - [x] 4.1 Rewrite `infra/lib/observability-stack.ts` for serverless monitoring
    - Remove Batch-specific metrics and alarms
    - Add alarm: `ExecutionsFailed >= 1` in 1-minute period on Step Functions
    - Add alarm: Lambda error rate > 5% over 5 minutes (min 10 invocations), treat missing as notBreaching
    - Add alarm: `ExecutionTime > 1800000ms` (30 min) on Step Functions
    - Add alarm: DLQ `ApproximateNumberOfMessagesVisible >= 1`
    - Add alarm: Billing `EstimatedCharges > $1` on AWS/Billing namespace (6-hour period)
    - All alarms publish to the shared SNS topic
    - Set log retention to 30 days for Lambda log groups
    - Update dashboard widgets for Lambda/SFN metrics
    - Accept `stateMachine`, `lambdaFunctions`, `dlqQueue`, and `snsTopic` as stack props
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 14.6_

- [x] 5. Update CDK app entry point and synth validation
  - [x] 5.1 Rewrite `infra/bin/app.ts` to wire new stacks
    - Instantiate stacks in order: DataLake → Metadata → IAM → Orchestration → Observability
    - Pass cross-stack references (bucket, table, roles)
    - Remove ComputeStack import and instantiation
    - Preserve existing tags and environment configuration
    - Run `cdk synth --all` to validate templates compile
    - _Requirements: 2.1, 14.3_

- [x] 6. Checkpoint — Infrastructure compiles and synthesizes
  - Ensure `cd infra && npm ci && npx cdk synth --all` passes without errors.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Lambda handler functions (Python)
  - [x] 7.1 Create Lambda project structure and shared utilities
    - Create `lambdas/` directory with `shared/` module containing:
      - `models.py`: Data classes for DynamoDB record types (RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION)
      - `timestamps.py`: ISO 8601 UTC formatter (seconds precision)
      - `dynamo.py`: DynamoDB write helper with 3-retry exponential backoff
      - `s3_utils.py`: S3 read/write helpers
      - `audit.py`: Audit record construction functions
    - Create `lambdas/requirements.txt` with boto3, botocore
    - Create `lambdas/Dockerfile` pinned base image for Lambda container packaging
    - _Requirements: 5.4, 5.9, 11.2, 12.3_

  - [x] 7.2 Implement `lambdas/ingestion_trigger/handler.py`
    - Parse S3 event input (bucket, key, size) from Step Functions payload
    - Validate FASTQ extension (case-insensitive `.fastq.gz` or `.fq.gz`)
    - Generate `run_id` from timestamp + sample + region
    - Compute SHA-256 checksums of input files
    - Return `{run_id, sample_id, input_checksums}` to Step Functions
    - Write AUDIT record: action `INGESTION_STARTED`
    - _Requirements: 2.3, 3.1, 3.3, 11.1_

  - [x] 7.3 Implement `lambdas/qc_orchestrator/handler.py`
    - Read FASTQ from S3, trigger QC analysis
    - Write QC output metrics to S3 `work/<run_id>/qc/`
    - Return `{qc_metrics}` (duplication rate, read stats)
    - Structured JSON logging with run_id
    - _Requirements: 1.1, 6.1_

  - [x] 7.4 Implement `lambdas/variant_calling/handler.py`
    - Invoke variant caller on aligned data
    - Support caller selection (HaplotypeCaller default, DeepVariant optional)
    - Write VCF output to S3 `work/<run_id>/called/`
    - Return `{vcf_key, caller, n_variants}`
    - _Requirements: 1.1, 1.8_

  - [x] 7.5 Implement `lambdas/validation_checker/handler.py`
    - Compare VCF against truth set
    - Calculate SNV precision, recall, F1
    - Determine `validation_pass` flag (F1 ≥ 0.99 → true)
    - Return `{precision, recall, f1, validation_pass}`
    - If validation fails, prepare AUDIT record with action `VALIDATION_FAILED` and F1 score
    - _Requirements: 1.3, 11.5_

  - [x] 7.6 Implement `lambdas/export_handler/handler.py`
    - Build `metrics.json` with full provenance stamp (git commit, versions, checksums)
    - Write `metrics.json` and `metrics.parquet` to S3 `results/<run_id>/`
    - Return `{export_key}`
    - _Requirements: 1.4, 4.1, 11.1_

  - [x] 7.7 Implement `lambdas/metadata_ingestor/handler.py`
    - Write RUN, QC_METRICS, PROVENANCE, and AUDIT records to DynamoDB
    - Validate `record_type` against allowed values (RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION)
    - Include `created_at` timestamp (ISO 8601 UTC, seconds precision) on all records
    - Include `sample_id` for GSI queryability
    - Handle DynamoDB write failures with 3 retries + exponential backoff
    - On retry exhaustion: publish CloudWatch alarm and raise error for Step Functions failure state
    - Sync write to local Postgres for Metabase (via shared utility)
    - Return `{ingested: true}`
    - _Requirements: 5.2, 5.4, 5.5, 5.6, 5.9, 8.5, 11.2_

  - [x] 7.8 Implement `lambdas/report_generator/handler.py`
    - Read `metrics.json` from S3
    - Invoke RAG reporter (or fall back to offline template)
    - Apply `enforce_guardrails()` on generated report
    - Write report to S3 `results/<run_id>/report.txt`
    - Write AUDIT record: action `REPORT_DRAFTED` with model version and adapter version
    - Write AUDIT record: action `WORKFLOW_COMPLETE` with execution timestamps
    - Return `{report_key}`
    - _Requirements: 9.4, 9.6, 9.7, 11.3_

- [x] 8. Checkpoint — Lambda handlers implemented and importable
  - Ensure all Lambda handler modules import without errors (`python -c "import lambdas.ingestion_trigger.handler"` etc.).
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Build RAG layer — FAISS vector store and retrieval
  - [x] 9.1 Create RAG module structure and embedding pipeline
    - Create `ai-report/rag/` directory with:
      - `build_index.py`: Script to build FAISS index from ClinVar/ClinGen annotations for chr20 genes
      - `embeddings.py`: Wrapper around `sentence-transformers/all-MiniLM-L6-v2` for embedding queries
      - `retriever.py`: FAISS search with cosine similarity filtering (≥ 0.70 threshold, top-5 max)
      - `__init__.py`: Package exports
    - Create `ai-report/rag/data/` with sample annotation JSONL for chr20 genes (≥1 entry per gene in target region)
    - Add `sentence-transformers`, `faiss-cpu` to `ai-report/requirements.txt`
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 9.2 Implement RAG-augmented report generation in `ai-report/infer.py`
    - Add `--rag` flag to `infer.py` that enables retrieval-augmented generation
    - Parse `metrics.json` to extract gene/variant identifiers
    - Embed query using sentence-transformers
    - Retrieve top-5 passages (cosine similarity ≥ 0.70) from FAISS index
    - Construct prompt: system instructions + retrieved passages + structured metrics
    - Call Ollama API (phi3:mini or llama3.2:3b) with 120-second timeout
    - Enforce word count bounds [120, 300] on report body
    - On Ollama failure (timeout, OOM, missing model): fall back to `render_offline()` and log warning
    - Apply `enforce_guardrails()` on all outputs
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 9.3 Create Dockerfile for RAG reporter container
    - Create `ai-report/Dockerfile` with FAISS, sentence-transformers, Ollama client, and inference code
    - Pin base image by sha256 digest
    - Include vector store index and model files in image
    - Pin all Python dependencies to exact versions
    - _Requirements: 12.5, 12.6_

- [x] 10. Implement DynamoDB-to-Postgres sync for Metabase bridge
  - [x] 10.1 Create sync script for local development
    - Create `db/sync_dynamodb_to_postgres.py`
    - Read DynamoDB items and insert into existing Postgres schema (runs, qc_metrics, run_provenance, audit_log tables)
    - Map DynamoDB single-table records to normalized Postgres tables
    - Use existing `v_run_summary` view for Metabase queries
    - Handle idempotent inserts (skip duplicates based on run_id)
    - Target < 5 minute latency from DynamoDB write to Postgres visibility
    - _Requirements: 8.5, 8.6_

- [x] 11. Checkpoint — End-to-end data flow testable locally
  - Ensure Lambda handlers + RAG + Postgres sync can be invoked in sequence locally.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Write property-based tests (Hypothesis)
  - [x] 12.1 Write property test for provenance stamp round-trip
    - **Property 1: Provenance Stamp Round-Trip**
    - Generate arbitrary provenance data (git SHA, semver, tool versions, checksums)
    - Serialize to metrics.json format, deserialize back
    - Assert all fields preserved exactly
    - **Validates: Requirements 1.4, 11.1**

  - [x] 12.2 Write property test for validation outcome determination
    - **Property 2: Validation Outcome Determination**
    - Generate arbitrary F1 scores in [0.0, 1.0]
    - Assert `validation_pass == (f1 >= 0.99)`
    - Assert VALIDATION_FAILED audit record produced when pass is false
    - **Validates: Requirements 1.3, 11.5**

  - [x] 12.3 Write property test for exit code classification
    - **Property 3: Exit Code Classification**
    - Generate arbitrary integers
    - Assert retryable iff code ∈ {137, 143, 104, 134, 139}
    - Assert non-retryable produces structured error with process name, exit code, stderr
    - **Validates: Requirements 1.6**

  - [x] 12.4 Write property test for S3 key pattern matching
    - **Property 4: EventBridge S3 Key Pattern Matching**
    - Generate arbitrary S3 key strings
    - Assert trigger iff key starts with `raw/` AND ends with `.fastq.gz` or `.fq.gz` (case-insensitive)
    - **Validates: Requirements 3.1, 3.3**

  - [x] 12.5 Write property test for record type validation
    - **Property 5: DynamoDB Record Type Validation**
    - Generate arbitrary strings
    - Assert accepted iff value ∈ {RUN, QC_METRICS, PROVENANCE, AUDIT, CORRECTION}
    - **Validates: Requirements 5.2**

  - [x] 12.6 Write property test for ISO 8601 timestamp formatting
    - **Property 6: ISO 8601 Timestamp Formatting**
    - Generate arbitrary datetimes
    - Assert output matches `YYYY-MM-DDTHH:MM:SSZ` pattern
    - Assert round-trip: parse(format(dt)) == dt truncated to seconds
    - **Validates: Requirements 5.4**

  - [x] 12.7 Write property test for audit record — completion
    - **Property 7: Audit Record Construction — Completion**
    - Generate arbitrary run_id, start time, end time
    - Assert output contains all required fields with correct values
    - Assert `action == "WORKFLOW_COMPLETE"`
    - **Validates: Requirements 2.3**

  - [x] 12.8 Write property test for audit record — failure
    - **Property 8: Audit Record Construction — Failure**
    - Generate arbitrary run_id, failed state name, error cause
    - Assert output contains all required fields
    - Assert `action == "WORKFLOW_FAILED"` and `failed_state` matches input
    - **Validates: Requirements 2.5**

  - [x] 12.9 Write property test for correction record integrity
    - **Property 9: Correction Record Integrity**
    - Generate arbitrary original record and correction data
    - Assert CORRECTION record contains `original_record_type`, `correction_reason`, corrected values
    - Assert original record is unchanged
    - **Validates: Requirements 5.7**

  - [x] 12.10 Write property test for guardrails enforcement
    - **Property 10: Guardrails Enforcement**
    - Generate arbitrary text strings including clinical phrases
    - Assert output contains banner `AI-DRAFTED — REQUIRES CLINICIAN REVIEW`
    - Assert output contains `Provenance:` line
    - Assert zero clinical recommendation patterns in output
    - **Validates: Requirements 9.6**

  - [x] 12.11 Write property test for RAG retrieval constraints
    - **Property 11: RAG Retrieval Constraints**
    - Generate arbitrary query embeddings and vector store states
    - Assert at most 5 passages returned
    - Assert all returned passages have cosine similarity ≥ 0.70
    - Assert passages ordered by descending similarity
    - **Validates: Requirements 9.2, 9.3**

  - [x] 12.12 Write property test for report word count bounds
    - **Property 12: Report Word Count Bounds**
    - Generate report outputs from the LLM path
    - Assert body word count ∈ [120, 300] (excluding banner and provenance line)
    - **Validates: Requirements 9.4**

  - [x] 12.13 Write property test for model card completeness
    - **Property 13: Model Card Completeness**
    - Generate arbitrary training run outputs
    - Assert model card contains all required fields (lr, batch_size, grad_accum, epochs, lora_rank, lora_alpha, dataset_version, base_model, final_loss)
    - Assert no field is null or empty
    - **Validates: Requirements 10.6**

- [x] 13. Update CDK guardrail tests — assert no Batch/Fargate/NAT/RDS
  - [x] 13.1 Rewrite `infra/test/stacks.test.ts` for new stack structure
    - Update imports to use new stacks (Orchestration, Metadata, IAM)
    - Remove ComputeStack-related tests
    - Add cost guardrail assertions: zero resources of types `AWS::Batch::*`, `AWS::ECS::Service`, `AWS::EC2::NatGateway`, `AWS::RDS::*`, `AWS::Bedrock::*`, `AWS::SageMaker::Endpoint`, `AWS::Kendra::*`, `AWS::Comprehend::*`
    - Assert DynamoDB table is on-demand billing
    - Assert DynamoDB PITR is enabled
    - Assert Lambda memory ≤ 512 MB and timeout ≤ 15 min for all functions
    - Assert all IAM deny policies are present (DeleteItem, UpdateItem, DeleteTable, DeleteObject)
    - Assert no IAM policy grants `*` resource ARN or `iam:*` actions
    - Assert Step Functions retry config (MaxAttempts=2, IntervalSeconds=5, BackoffRate=2.0)
    - Assert billing alarm exists on EstimatedCharges > $1
    - Assert EventBridge DLQ exists with 14-day retention
    - Preserve existing data lake assertions (versioning, public access block, TLS)
    - _Requirements: 14.3, 14.4, 14.5, 7.4, 7.5_

  - [x] 13.2 Write unit tests for Lambda shared utilities
    - Test `timestamps.py` ISO 8601 formatting with edge cases
    - Test `dynamo.py` retry logic (mock boto3)
    - Test `models.py` record type validation
    - Test `audit.py` record construction
    - _Requirements: 5.2, 5.4, 5.9_

- [x] 14. Checkpoint — All tests pass
  - Run `cd infra && npm test` for CDK guardrail tests.
  - Run `pytest tests/` for Python tests.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Update CI workflows for new stack structure
  - [x] 15.1 Update `.github/workflows/infra-ci.yml`
    - Ensure `cdk synth --all` runs against new stack structure
    - Ensure `npm test` runs updated guardrail tests
    - Keep `tsc --noEmit` type-checking
    - Add validation that no Batch/Fargate/NAT resources appear in synthesized templates
    - Maintain 10-minute timeout
    - Maintain `contents: read` permissions
    - _Requirements: 13.3, 13.6, 13.7_

  - [x] 15.2 Update `.github/workflows/pipeline-ci.yml`
    - Add pytest execution for property-based tests (`tests/test_properties.py`)
    - Add Lambda handler import validation
    - Maintain existing nf-core lint, stub test, and guardrail test steps
    - Maintain ML smoke test step
    - Maintain 10–15 minute timeouts
    - _Requirements: 13.1, 13.2, 13.4, 13.5_

- [x] 16. Write production migration path documentation
  - [x] 16.1 Create `docs/PRODUCTION-MIGRATION.md`
    - Describe AWS HealthOmics as production path for pipeline execution (Nextflow private workflows)
    - Describe Aurora Serverless v2 as production replacement for DynamoDB
    - Describe Amazon Bedrock + Knowledge Bases as production replacement for local RAG
    - Describe SageMaker Training Jobs + Model Registry for production fine-tuning
    - Describe cost and operational trade-offs for each migration (table format)
    - Include architecture diagrams comparing demo vs. production
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 17. Final checkpoint — Full platform validation
  - Run full test suite: `pytest tests/`, `cd infra && npm test`, `cdk synth --all`.
  - Verify CI workflows are syntactically valid.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- CDK guardrail tests validate infrastructure invariants
- The existing Nextflow pipeline, AI guardrails engine, and Postgres schema are preserved — tasks build on top of them
- Lambda handlers are implemented as Python modules; CDK packages them as container images
- Local development uses docker-compose for Postgres + Metabase; DynamoDB-to-Postgres sync bridges the two data stores

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["7.1", "9.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "7.4", "7.5", "7.6", "9.2", "9.3"] },
    { "id": 6, "tasks": ["7.7", "7.8", "10.1"] },
    { "id": 7, "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6"] },
    { "id": 8, "tasks": ["12.7", "12.8", "12.9", "12.10", "12.11", "12.12", "12.13"] },
    { "id": 9, "tasks": ["13.1", "13.2"] },
    { "id": 10, "tasks": ["15.1", "15.2"] },
    { "id": 11, "tasks": ["16.1"] }
  ]
}
```
