import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';

interface IamStackProps extends cdk.StackProps {
  dataLakeBucket: s3.IBucket;
}

/**
 * Least-privilege IAM for AWS Batch jobs.
 *
 * The job role is deliberately narrow, and this is the part an ISO 15189 / NATA
 * infra review looks for:
 *   - read-only on raw/  (inputs must not be mutated by a compute job)
 *   - read/write on results/ and work/  (only where output belongs)
 *   - NO s3:DeleteObject on raw/ or results/  (deletion is not a pipeline capability)
 * The execution role is separate and only pulls images / writes logs.
 */
export class IamStack extends cdk.Stack {
  public readonly batchJobRole: iam.Role;
  public readonly batchExecutionRole: iam.Role;

  constructor(scope: Construct, id: string, props: IamStackProps) {
    super(scope, id, props);
    const bucketArn = props.dataLakeBucket.bucketArn;

    this.batchJobRole = new iam.Role(this, 'BatchJobRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Scoped role assumed by pipeline containers running on Batch',
    });

    // Read-only on inputs
    this.batchJobRole.addToPolicy(new iam.PolicyStatement({
      sid: 'ReadRawInputs',
      actions: ['s3:GetObject', 's3:ListBucket'],
      resources: [bucketArn, `${bucketArn}/raw/*`],
      conditions: { StringLike: { 's3:prefix': ['raw/*', 'results/*', 'work/*'] } },
    }));

    // Read/write only under results/ and work/
    this.batchJobRole.addToPolicy(new iam.PolicyStatement({
      sid: 'WriteResultsAndWork',
      actions: ['s3:GetObject', 's3:PutObject'],
      resources: [`${bucketArn}/results/*`, `${bucketArn}/work/*`],
    }));

    // Explicit deny on deleting inputs or results — deletion is not a job capability
    this.batchJobRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DenyDeleteImmutableData',
      effect: iam.Effect.DENY,
      actions: ['s3:DeleteObject', 's3:DeleteObjectVersion'],
      resources: [`${bucketArn}/raw/*`, `${bucketArn}/results/*`],
    }));

    this.batchExecutionRole = new iam.Role(this, 'BatchExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Pulls container images and ships logs to CloudWatch',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
    });

    new cdk.CfnOutput(this, 'BatchJobRoleArn', { value: this.batchJobRole.roleArn });
  }
}
