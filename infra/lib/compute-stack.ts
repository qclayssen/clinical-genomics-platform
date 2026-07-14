import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as batch from 'aws-cdk-lib/aws-batch';

interface ComputeStackProps extends cdk.StackProps {
  jobRole: iam.IRole;
  executionRole: iam.IRole;
}

/**
 * AWS Batch compute environment + queue that the Nextflow `awsbatch` executor targets.
 *
 * Uses Fargate for the pipeline steps: no EC2 hosts to patch or account for in a
 * security review, per-job isolation, and spot pricing for cost. A CPU-heavy caller
 * (DeepVariant) would move to an EC2/GPU compute env; kept Fargate here for a
 * reproducible, low-footprint portfolio deploy.
 */
export class ComputeStack extends cdk.Stack {
  public readonly jobQueue: batch.JobQueue;

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, 'CgpVpc', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
      ],
    });

    const computeEnv = new batch.FargateComputeEnvironment(this, 'CgpFargateCE', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }, // jobs run off the public internet
      spot: true,
      maxvCpus: 64,
    });

    this.jobQueue = new batch.JobQueue(this, 'CgpJobQueue', {
      computeEnvironments: [{ computeEnvironment: computeEnv, order: 1 }],
      priority: 1,
    });

    // A reference job definition; Nextflow overrides image/resources per process.
    new batch.EcsJobDefinition(this, 'CgpJobDef', {
      container: new batch.EcsFargateContainerDefinition(this, 'CgpJobContainer', {
        image: cdk.aws_ecs.ContainerImage.fromRegistry('public.ecr.aws/lts/ubuntu:22.04'),
        cpu: 2,
        memory: cdk.Size.gibibytes(4),
        jobRole: props.jobRole,
        executionRole: props.executionRole,
      }),
    });

    new cdk.CfnOutput(this, 'JobQueueName', {
      value: this.jobQueue.jobQueueName,
      description: 'Set CGP_BATCH_QUEUE to this for the Nextflow aws profile',
      exportName: 'CgpBatchQueue',
    });
  }
}
