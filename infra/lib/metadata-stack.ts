import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

/**
 * DynamoDB single-table metadata store for the genomics platform.
 *
 * Accreditation-relevant choices:
 *  - Single-table design with composite key (run_id + record_type) for all entities.
 *  - On-demand billing (PAY_PER_REQUEST) → $0 at demo scale, always-free tier.
 *  - Point-in-time recovery (PITR) → continuous backups for audit compliance.
 *  - Removal policy RETAIN → cdk destroy never deletes stored data.
 *  - GSI on sample_id + created_at → supports cohort queries ordered by time.
 *  - Append-only semantics enforced at IAM level (deny Delete/Update in iam-stack).
 */
export class MetadataStack extends cdk.Stack {
  public readonly metadataTable: dynamodb.Table;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.metadataTable = new dynamodb.Table(this, 'MetadataTable', {
      tableName: 'cgp-metadata',
      partitionKey: { name: 'run_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'record_type', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.metadataTable.addGlobalSecondaryIndex({
      indexName: 'sample_id-created_at-index',
      partitionKey: { name: 'sample_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'created_at', type: dynamodb.AttributeType.STRING },
    });

    new cdk.CfnOutput(this, 'MetadataTableName', {
      value: this.metadataTable.tableName,
      description: 'DynamoDB metadata table for run records, QC metrics, provenance, and audit trail',
      exportName: 'CgpMetadataTable',
    });

    new cdk.CfnOutput(this, 'MetadataTableArn', {
      value: this.metadataTable.tableArn,
      description: 'ARN of the DynamoDB metadata table for IAM policy references',
      exportName: 'CgpMetadataTableArn',
    });
  }
}
