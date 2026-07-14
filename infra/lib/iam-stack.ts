import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

export interface IamStackProps extends cdk.StackProps {
  dataLakeBucket: s3.IBucket;
  metadataTable: dynamodb.ITable;
}

/**
 * Per-Lambda least-privilege IAM roles for the Clinical Genomics Platform.
 *
 * Each Lambda function in the Step Functions workflow gets its own role scoped to
 * only the S3 prefixes and DynamoDB actions it requires. All roles carry explicit
 * DENY policies to enforce append-only semantics and prevent privilege escalation.
 *
 * Accreditation-relevant choices:
 *  - 7 separate roles (one per Lambda) — no shared overprivileged role
 *  - Explicit DENY on DynamoDB Delete/Update/DeleteTable — append-only at IAM level
 *  - Explicit DENY on S3 DeleteObject/DeleteObjectVersion on raw/* and results/*
 *  - No role grants `*` as resource ARN or includes any `iam:*` action
 *  - No role includes iam:CreatePolicy, iam:AttachRolePolicy, iam:PutRolePolicy, or sts:AssumeRole
 */
export class IamStack extends cdk.Stack {
  public readonly ingestionTriggerRole: iam.Role;
  public readonly qcOrchestratorRole: iam.Role;
  public readonly variantCallingRole: iam.Role;
  public readonly validationCheckerRole: iam.Role;
  public readonly exportHandlerRole: iam.Role;
  public readonly metadataIngestorRole: iam.Role;
  public readonly reportGeneratorRole: iam.Role;

  /** All 7 Lambda roles keyed by function name for easy cross-stack reference. */
  public readonly lambdaRoles: Record<string, iam.Role>;

  constructor(scope: Construct, id: string, props: IamStackProps) {
    super(scope, id, props);

    const bucketArn = props.dataLakeBucket.bucketArn;
    const tableArn = props.metadataTable.tableArn;

    // --- Helper: create a Lambda role with CloudWatch Logs permissions ---
    const createLambdaRole = (name: string, description: string): iam.Role => {
      const role = new iam.Role(this, name, {
        roleName: `cgp-${name}`,
        assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
        description,
      });

      // CloudWatch Logs — all Lambdas need this
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'CloudWatchLogs',
        actions: [
          'logs:CreateLogGroup',
          'logs:CreateLogStream',
          'logs:PutLogEvents',
        ],
        resources: [
          `arn:${cdk.Aws.PARTITION}:logs:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:log-group:/aws/lambda/cgp-*`,
        ],
      }));

      return role;
    };

    // =========================================================================
    // 1. Ingestion Trigger Role
    //    Reads raw/* (validate FASTQ), writes work/* (stage for processing)
    // =========================================================================
    this.ingestionTriggerRole = createLambdaRole(
      'IngestionTriggerRole',
      'Reads raw FASTQ inputs from S3 and stages them for processing',
    );

    this.ingestionTriggerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ReadRaw',
      actions: ['s3:GetObject'],
      resources: [`${bucketArn}/raw/*`],
    }));

    this.ingestionTriggerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ListBucket',
      actions: ['s3:ListBucket'],
      resources: [bucketArn],
      conditions: { StringLike: { 's3:prefix': ['raw/*'] } },
    }));

    this.ingestionTriggerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3WriteWork',
      actions: ['s3:PutObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    // =========================================================================
    // 2. QC Orchestrator Role
    //    Reads raw/* and work/*, writes work/*
    // =========================================================================
    this.qcOrchestratorRole = createLambdaRole(
      'QcOrchestratorRole',
      'Runs QC analysis on raw/work data and writes QC metrics',
    );

    this.qcOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ReadRawAndWork',
      actions: ['s3:GetObject'],
      resources: [`${bucketArn}/raw/*`, `${bucketArn}/work/*`],
    }));

    this.qcOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3WriteWork',
      actions: ['s3:PutObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    // =========================================================================
    // 3. Variant Calling Role
    //    Reads work/*, writes work/*
    // =========================================================================
    this.variantCallingRole = createLambdaRole(
      'VariantCallingRole',
      'Invokes variant caller on aligned data in work/',
    );

    this.variantCallingRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ReadWork',
      actions: ['s3:GetObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    this.variantCallingRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3WriteWork',
      actions: ['s3:PutObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    // =========================================================================
    // 4. Validation Checker Role
    //    Reads work/*, writes work/*
    // =========================================================================
    this.validationCheckerRole = createLambdaRole(
      'ValidationCheckerRole',
      'Compares VCF against truth set for validation',
    );

    this.validationCheckerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ReadWork',
      actions: ['s3:GetObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    this.validationCheckerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3WriteWork',
      actions: ['s3:PutObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    // =========================================================================
    // 5. Export Handler Role
    //    Reads work/*, writes results/*
    // =========================================================================
    this.exportHandlerRole = createLambdaRole(
      'ExportHandlerRole',
      'Exports metrics and provenance to results/ prefix',
    );

    this.exportHandlerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ReadWork',
      actions: ['s3:GetObject'],
      resources: [`${bucketArn}/work/*`],
    }));

    this.exportHandlerRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3WriteResults',
      actions: ['s3:PutObject'],
      resources: [`${bucketArn}/results/*`],
    }));

    // =========================================================================
    // 6. Metadata Ingestor Role
    //    DynamoDB PutItem, GetItem, Query on metadata table (no S3 access needed)
    // =========================================================================
    this.metadataIngestorRole = createLambdaRole(
      'MetadataIngestorRole',
      'Writes run metadata, QC metrics, provenance, and audit records to DynamoDB',
    );

    this.metadataIngestorRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DynamoDBWrite',
      actions: [
        'dynamodb:PutItem',
        'dynamodb:GetItem',
        'dynamodb:Query',
      ],
      resources: [tableArn, `${tableArn}/index/*`],
    }));

    // =========================================================================
    // 7. Report Generator Role
    //    Reads results/*, writes results/*, DynamoDB PutItem (audit records)
    // =========================================================================
    this.reportGeneratorRole = createLambdaRole(
      'ReportGeneratorRole',
      'Generates AI-drafted reports and writes audit trail records',
    );

    this.reportGeneratorRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3ReadResults',
      actions: ['s3:GetObject'],
      resources: [`${bucketArn}/results/*`],
    }));

    this.reportGeneratorRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3WriteResults',
      actions: ['s3:PutObject'],
      resources: [`${bucketArn}/results/*`],
    }));

    this.reportGeneratorRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DynamoDBPutItem',
      actions: ['dynamodb:PutItem'],
      resources: [tableArn],
    }));

    // =========================================================================
    // Explicit DENY policies — applied to ALL roles
    // =========================================================================

    const allRoles = [
      this.ingestionTriggerRole,
      this.qcOrchestratorRole,
      this.variantCallingRole,
      this.validationCheckerRole,
      this.exportHandlerRole,
      this.metadataIngestorRole,
      this.reportGeneratorRole,
    ];

    for (const role of allRoles) {
      // DENY: DynamoDB Delete/Update/DeleteTable on metadata table
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'DenyDynamoDBMutations',
        effect: iam.Effect.DENY,
        actions: [
          'dynamodb:DeleteItem',
          'dynamodb:UpdateItem',
          'dynamodb:DeleteTable',
        ],
        resources: [tableArn],
      }));

      // DENY: S3 DeleteObject/DeleteObjectVersion on raw/* and results/*
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'DenyS3DeleteImmutableData',
        effect: iam.Effect.DENY,
        actions: ['s3:DeleteObject', 's3:DeleteObjectVersion'],
        resources: [`${bucketArn}/raw/*`, `${bucketArn}/results/*`],
      }));

      // DENY: IAM privilege escalation actions
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'DenyPrivilegeEscalation',
        effect: iam.Effect.DENY,
        actions: [
          'iam:CreatePolicy',
          'iam:AttachRolePolicy',
          'iam:PutRolePolicy',
          'sts:AssumeRole',
        ],
        resources: ['*'],
      }));
    }

    // =========================================================================
    // Export roles as a Record for easy cross-stack reference
    // =========================================================================
    this.lambdaRoles = {
      ingestionTrigger: this.ingestionTriggerRole,
      qcOrchestrator: this.qcOrchestratorRole,
      variantCalling: this.variantCallingRole,
      validationChecker: this.validationCheckerRole,
      exportHandler: this.exportHandlerRole,
      metadataIngestor: this.metadataIngestorRole,
      reportGenerator: this.reportGeneratorRole,
    };

    // =========================================================================
    // Outputs
    // =========================================================================
    new cdk.CfnOutput(this, 'LambdaRoleArns', {
      value: JSON.stringify(
        Object.fromEntries(
          Object.entries(this.lambdaRoles).map(([k, r]) => [k, r.roleArn]),
        ),
      ),
      description: 'ARNs of all per-Lambda IAM roles',
    });
  }
}
