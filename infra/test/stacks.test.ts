import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { DataLakeStack } from '../lib/data-lake-stack';
import { IamStack } from '../lib/iam-stack';

/**
 * Guardrail tests — these encode the accreditation-relevant invariants so a
 * regression (e.g. someone turns off versioning) fails CI instead of shipping.
 */
describe('CGP infrastructure invariants', () => {
  const app = new cdk.App();
  const dataLake = new DataLakeStack(app, 'TestDataLake');
  const iam = new IamStack(app, 'TestIam', { dataLakeBucket: dataLake.bucket });

  const lakeTemplate = Template.fromStack(dataLake);
  const iamTemplate = Template.fromStack(iam);

  test('data lake bucket has versioning enabled', () => {
    lakeTemplate.hasResourceProperties('AWS::S3::Bucket', {
      VersioningConfiguration: { Status: 'Enabled' },
    });
  });

  test('data lake blocks all public access', () => {
    lakeTemplate.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    });
  });

  test('data lake enforces TLS-only access', () => {
    lakeTemplate.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Effect: 'Deny',
            Condition: { Bool: { 'aws:SecureTransport': 'false' } },
          }),
        ]),
      },
    });
  });

  test('batch job role explicitly denies deleting raw/results data', () => {
    iamTemplate.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Effect: 'Deny',
            Action: Match.arrayWith(['s3:DeleteObject']),
          }),
        ]),
      },
    });
  });
});
