#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { DataLakeStack } from '../lib/data-lake-stack';
import { MetadataStack } from '../lib/metadata-stack';
import { IamStack } from '../lib/iam-stack';
import { OrchestrationStack } from '../lib/orchestration-stack';
import { ObservabilityStack } from '../lib/observability-stack';
import { DemoHostingStack } from '../lib/demo-hosting-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? 'ap-southeast-2',
};

// Common tags — an accreditation reviewer wants to see data classification and
// ownership on every resource.
const tags = {
  Project: 'clinical-genomics-platform',
  DataClassification: 'research-public', // GIAB is public; real clinical data would be 'restricted'
  Owner: 'quentin.clayssen',
  ManagedBy: 'cdk',
};

// 1. Data Lake — S3 bucket with versioning, encryption, lifecycle
const dataLake = new DataLakeStack(app, 'CgpDataLake', { env, tags });

// 2. Metadata — DynamoDB single-table design
const metadata = new MetadataStack(app, 'CgpMetadata', { env, tags });

// 3. IAM — per-Lambda least-privilege roles
const iam = new IamStack(app, 'CgpIam', {
  env,
  tags,
  dataLakeBucket: dataLake.bucket,
  metadataTable: metadata.metadataTable,
});

// 4. Orchestration — Step Functions + Lambda + EventBridge
const orchestration = new OrchestrationStack(app, 'CgpOrchestration', {
  env,
  tags,
  dataLakeBucket: dataLake.bucket,
  metadataTable: metadata.metadataTable,
  lambdaRoles: iam.lambdaRoles,
});

// 5. Observability — CloudWatch alarms, log groups, dashboard
new ObservabilityStack(app, 'CgpObservability', {
  env,
  tags,
  stateMachine: orchestration.stateMachine,
  lambdaFunctions: orchestration.lambdaFunctions,
  dlqQueue: orchestration.dlqQueue,
  snsTopic: orchestration.snsTopic,
});

// 6. Demo Hosting — EC2 t2.micro (free tier) running Docker Compose
//    Streamlit demo on :8501, Metabase on :3000, Postgres internal
//    Requires real AWS credentials (uses Vpc.fromLookup for the default VPC).
//    Skipped in CI where CDK_DEFAULT_ACCOUNT is a dummy placeholder.
const isRealAccount = env.account && env.account !== '000000000000';
if (isRealAccount) {
  new DemoHostingStack(app, 'CgpDemoHosting', { env, tags });
}

app.synth();
