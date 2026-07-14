import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { DataLakeStack } from '../lib/data-lake-stack';
import { MetadataStack } from '../lib/metadata-stack';
import { IamStack } from '../lib/iam-stack';
import { OrchestrationStack } from '../lib/orchestration-stack';
import { ObservabilityStack } from '../lib/observability-stack';

/**
 * Guardrail tests — these encode the accreditation-relevant invariants so a
 * regression (e.g. someone turns off versioning) fails CI instead of shipping.
 */
describe('CGP infrastructure invariants', () => {
  const app = new cdk.App();
  const dataLake = new DataLakeStack(app, 'TestDataLake');
  const metadata = new MetadataStack(app, 'TestMetadata');
  const iam = new IamStack(app, 'TestIam', {
    dataLakeBucket: dataLake.bucket,
    metadataTable: metadata.metadataTable,
  });
  const orchestration = new OrchestrationStack(app, 'TestOrchestration', {
    dataLakeBucket: dataLake.bucket,
    metadataTable: metadata.metadataTable,
    lambdaRoles: iam.lambdaRoles,
  });
  const observability = new ObservabilityStack(app, 'TestObservability', {
    stateMachine: orchestration.stateMachine,
    lambdaFunctions: orchestration.lambdaFunctions,
    dlqQueue: orchestration.dlqQueue,
    snsTopic: orchestration.snsTopic,
  });

  const lakeTemplate = Template.fromStack(dataLake);
  const metadataTemplate = Template.fromStack(metadata);
  const iamTemplate = Template.fromStack(iam);
  const orchestrationTemplate = Template.fromStack(orchestration);
  const observabilityTemplate = Template.fromStack(observability);

  // All templates collected for cross-stack assertions
  const allTemplates = [
    { name: 'DataLake', template: lakeTemplate },
    { name: 'Metadata', template: metadataTemplate },
    { name: 'IAM', template: iamTemplate },
    { name: 'Orchestration', template: orchestrationTemplate },
    { name: 'Observability', template: observabilityTemplate },
  ];

  // =========================================================================
  // 1. Data Lake — preserve existing assertions
  // =========================================================================
  describe('Data Lake', () => {
    test('bucket has versioning enabled', () => {
      lakeTemplate.hasResourceProperties('AWS::S3::Bucket', {
        VersioningConfiguration: { Status: 'Enabled' },
      });
    });

    test('bucket blocks all public access', () => {
      lakeTemplate.hasResourceProperties('AWS::S3::Bucket', {
        PublicAccessBlockConfiguration: {
          BlockPublicAcls: true,
          BlockPublicPolicy: true,
          IgnorePublicAcls: true,
          RestrictPublicBuckets: true,
        },
      });
    });

    test('bucket enforces TLS-only access', () => {
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
  });

  // =========================================================================
  // 2. Cost guardrails — assert zero resources of banned types
  // =========================================================================
  describe('Cost guardrails', () => {
    const bannedResourcePrefixes = [
      'AWS::Batch::',
      'AWS::ECS::Service',
      'AWS::EC2::NatGateway',
      'AWS::RDS::',
      'AWS::Bedrock::',
      'AWS::SageMaker::Endpoint',
      'AWS::Kendra::',
      'AWS::Comprehend::',
    ];

    for (const { name, template } of allTemplates) {
      for (const banned of bannedResourcePrefixes) {
        test(`${name} stack has zero ${banned} resources`, () => {
          const resources = template.toJSON().Resources ?? {};
          const matches = Object.values(resources).filter((r: any) => {
            const type: string = r.Type ?? '';
            if (banned.endsWith('::')) {
              return type.startsWith(banned);
            }
            return type === banned;
          });
          expect(matches).toHaveLength(0);
        });
      }
    }
  });

  // =========================================================================
  // 3. DynamoDB — on-demand billing and PITR
  // =========================================================================
  describe('DynamoDB', () => {
    test('metadata table uses on-demand billing', () => {
      metadataTemplate.hasResourceProperties('AWS::DynamoDB::Table', {
        BillingMode: 'PAY_PER_REQUEST',
      });
    });

    test('metadata table has PITR enabled', () => {
      metadataTemplate.hasResourceProperties('AWS::DynamoDB::Table', {
        PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
      });
    });
  });

  // =========================================================================
  // 4. Lambda — memory ≤ 512 MB and timeout ≤ 15 min (900 seconds)
  // =========================================================================
  describe('Lambda', () => {
    test('all Lambda functions have memory ≤ 512 MB', () => {
      const resources = orchestrationTemplate.toJSON().Resources ?? {};
      const lambdaFunctions = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::Lambda::Function',
      );
      expect(lambdaFunctions.length).toBeGreaterThan(0);
      for (const fn of lambdaFunctions as any[]) {
        expect(fn.Properties.MemorySize).toBeLessThanOrEqual(512);
      }
    });

    test('all Lambda functions have timeout ≤ 900 seconds (15 min)', () => {
      const resources = orchestrationTemplate.toJSON().Resources ?? {};
      const lambdaFunctions = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::Lambda::Function',
      );
      expect(lambdaFunctions.length).toBeGreaterThan(0);
      for (const fn of lambdaFunctions as any[]) {
        expect(fn.Properties.Timeout).toBeLessThanOrEqual(900);
      }
    });
  });

  // =========================================================================
  // 5. IAM — deny policies and no wildcard resource/iam:* in non-deny
  // =========================================================================
  describe('IAM', () => {
    test('deny policies include DeleteItem, UpdateItem, DeleteTable, and DeleteObject', () => {
      const resources = iamTemplate.toJSON().Resources ?? {};
      const policies = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::IAM::Policy',
      );

      const denyActions = new Set<string>();
      for (const policy of policies as any[]) {
        const statements = policy.Properties?.PolicyDocument?.Statement ?? [];
        for (const stmt of statements) {
          if (stmt.Effect === 'Deny') {
            const actions = Array.isArray(stmt.Action) ? stmt.Action : [stmt.Action];
            actions.forEach((a: string) => denyActions.add(a));
          }
        }
      }

      expect(denyActions).toContain('dynamodb:DeleteItem');
      expect(denyActions).toContain('dynamodb:UpdateItem');
      expect(denyActions).toContain('dynamodb:DeleteTable');
      expect(denyActions).toContain('s3:DeleteObject');
    });

    test('no IAM policy grants * resource ARN in non-deny statements (except DenyPrivilegeEscalation)', () => {
      const resources = iamTemplate.toJSON().Resources ?? {};
      const policies = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::IAM::Policy',
      );

      for (const policy of policies as any[]) {
        const statements = policy.Properties?.PolicyDocument?.Statement ?? [];
        for (const stmt of statements) {
          // Skip deny statements — deny on * is acceptable (e.g., DenyPrivilegeEscalation)
          if (stmt.Effect === 'Deny') continue;

          const resources = Array.isArray(stmt.Resource) ? stmt.Resource : [stmt.Resource];
          for (const resource of resources) {
            expect(resource).not.toBe('*');
          }
        }
      }
    });

    test('no IAM policy grants iam:* actions', () => {
      const resources = iamTemplate.toJSON().Resources ?? {};
      const policies = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::IAM::Policy',
      );

      for (const policy of policies as any[]) {
        const statements = policy.Properties?.PolicyDocument?.Statement ?? [];
        for (const stmt of statements) {
          const actions = Array.isArray(stmt.Action) ? stmt.Action : [stmt.Action];
          for (const action of actions) {
            expect(action).not.toBe('iam:*');
          }
        }
      }
    });
  });

  // =========================================================================
  // 6. Step Functions — retry configuration
  // =========================================================================
  describe('Step Functions', () => {
    test('state machine has retry config with MaxAttempts=2, IntervalSeconds=5, BackoffRate=2.0', () => {
      const resources = orchestrationTemplate.toJSON().Resources ?? {};
      const stateMachines = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::StepFunctions::StateMachine',
      );
      expect(stateMachines.length).toBeGreaterThan(0);

      for (const sm of stateMachines as any[]) {
        const definitionString = sm.Properties?.DefinitionString;
        // DefinitionString is Fn::Join with Ref tokens for ARNs — replace refs with placeholder strings
        let definition: any;
        if (typeof definitionString === 'string') {
          definition = JSON.parse(definitionString);
        } else if (definitionString?.['Fn::Join']) {
          // CDK uses Fn::Join with Ref/GetAtt tokens embedded in the string.
          // Non-string parts (Refs) appear mid-string, so replace with a placeholder.
          const parts = definitionString['Fn::Join'][1];
          const joined = parts.map((p: any) => (typeof p === 'string' ? p : 'PLACEHOLDER')).join('');
          definition = JSON.parse(joined);
        } else {
          definition = definitionString;
        }

        // Find states with Retry configuration
        const states = definition?.States ?? {};
        const statesWithRetry = Object.values(states).filter(
          (s: any) => Array.isArray(s.Retry) && s.Retry.length > 0,
        );
        expect(statesWithRetry.length).toBeGreaterThan(0);

        // Check the user-defined retry (States.ALL) — CDK also adds SDK retries automatically
        for (const state of statesWithRetry as any[]) {
          const userRetry = state.Retry.find(
            (r: any) => Array.isArray(r.ErrorEquals) && r.ErrorEquals.includes('States.ALL'),
          );
          expect(userRetry).toBeDefined();
          expect(userRetry.MaxAttempts).toBe(2);
          expect(userRetry.IntervalSeconds).toBe(5);
          expect(userRetry.BackoffRate).toBe(2.0);
        }
      }
    });
  });

  // =========================================================================
  // 7. Observability — billing alarm and DLQ retention
  // =========================================================================
  describe('Observability', () => {
    test('billing alarm exists on EstimatedCharges > $1', () => {
      observabilityTemplate.hasResourceProperties('AWS::CloudWatch::Alarm', {
        Namespace: 'AWS/Billing',
        MetricName: 'EstimatedCharges',
        Threshold: 1,
      });
    });

    test('EventBridge DLQ exists with 14-day retention', () => {
      orchestrationTemplate.hasResourceProperties('AWS::SQS::Queue', {
        MessageRetentionPeriod: 1209600, // 14 days in seconds
      });
    });
  });
});
