import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';

/**
 * S3 data lake for the genomics platform.
 *
 * Accreditation-relevant choices:
 *  - Versioning ON  -> objects are never silently overwritten (audit trail).
 *  - Object Lock (governance) -> results can't be deleted before retention elapses.
 *  - Encryption at rest + TLS-only bucket policy.
 *  - Public access fully blocked.
 *  - Lifecycle tiering keeps cost sane without deleting anything.
 */
export class DataLakeStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.bucket = new s3.Bucket(this, 'DataLake', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      objectLockEnabled: true,
      objectLockDefaultRetention: s3.ObjectLockRetention.governance(cdk.Duration.days(90)),
      removalPolicy: cdk.RemovalPolicy.RETAIN, // never auto-delete a data lake
      lifecycleRules: [
        {
          id: 'tier-interim-then-expire-work',
          prefix: 'work/', // Nextflow scratch — safe to expire
          expiration: cdk.Duration.days(14),
        },
        {
          id: 'archive-raw-inputs',
          prefix: 'raw/',
          transitions: [
            { storageClass: s3.StorageClass.INFREQUENT_ACCESS, transitionAfter: cdk.Duration.days(30) },
            { storageClass: s3.StorageClass.GLACIER, transitionAfter: cdk.Duration.days(180) },
          ],
        },
      ],
    });

    new cdk.CfnOutput(this, 'DataLakeBucketName', {
      value: this.bucket.bucketName,
      description: 'Set CGP_S3_BUCKET to this for the Nextflow aws profile',
      exportName: 'CgpDataLakeBucket',
    });
  }
}
