#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { DataLakeStack } from '../lib/data-lake-stack';
import { ComputeStack } from '../lib/compute-stack';
import { IamStack } from '../lib/iam-stack';
import { ObservabilityStack } from '../lib/observability-stack';

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

const dataLake = new DataLakeStack(app, 'CgpDataLake', { env, tags });

const iam = new IamStack(app, 'CgpIam', {
  env,
  tags,
  dataLakeBucket: dataLake.bucket,
});

const compute = new ComputeStack(app, 'CgpCompute', {
  env,
  tags,
  jobRole: iam.batchJobRole,
  executionRole: iam.batchExecutionRole,
});

new ObservabilityStack(app, 'CgpObservability', {
  env,
  tags,
  jobQueueName: compute.jobQueue.jobQueueName,
});

app.synth();
