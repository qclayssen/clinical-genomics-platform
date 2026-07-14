import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

export interface OrchestrationStackProps extends cdk.StackProps {
  dataLakeBucket: s3.IBucket;
  metadataTable: dynamodb.ITable;
  lambdaRoles: Record<string, iam.IRole>;
}

/**
 * Serverless orchestration layer for the Clinical Genomics Platform.
 *
 * Replaces the previous AWS Batch/Fargate compute stack with:
 *  - 7 Lambda functions (one per pipeline stage)
 *  - Step Functions state machine orchestrating the full workflow
 *  - EventBridge rule triggering on S3 PutObject for raw/*.fastq.gz
 *  - SQS dead-letter queue for failed EventBridge deliveries
 *  - SNS topic for failure notifications
 *
 * All resources stay within AWS free-tier limits at demo scale.
 */
export class OrchestrationStack extends cdk.Stack {
  public readonly stateMachine: sfn.StateMachine;
  public readonly lambdaFunctions: lambda.Function[];
  public readonly dlqQueue: sqs.Queue;
  public readonly snsTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: OrchestrationStackProps) {
    super(scope, id, props);

    // =========================================================================
    // SNS Topic — failure notifications
    // =========================================================================
    this.snsTopic = new sns.Topic(this, 'FailureNotificationTopic', {
      topicName: 'cgp-workflow-failures',
      displayName: 'CGP Workflow Failure Notifications',
    });

    // =========================================================================
    // SQS Dead-Letter Queue — failed EventBridge deliveries (14-day retention)
    // =========================================================================
    this.dlqQueue = new sqs.Queue(this, 'EventBridgeDLQ', {
      queueName: 'cgp-eventbridge-dlq',
      retentionPeriod: cdk.Duration.days(14),
    });

    // =========================================================================
    // Lambda Functions — 7 orchestrator functions
    // =========================================================================
    const lambdaConfig: Array<{
      id: string;
      functionName: string;
      memorySize: number;
      timeout: cdk.Duration;
      roleKey: string;
    }> = [
      { id: 'IngestionTrigger', functionName: 'cgp-ingestion-trigger', memorySize: 256, timeout: cdk.Duration.seconds(60), roleKey: 'ingestionTrigger' },
      { id: 'QcOrchestrator', functionName: 'cgp-qc-orchestrator', memorySize: 512, timeout: cdk.Duration.minutes(15), roleKey: 'qcOrchestrator' },
      { id: 'VariantCalling', functionName: 'cgp-variant-calling', memorySize: 512, timeout: cdk.Duration.minutes(15), roleKey: 'variantCalling' },
      { id: 'ValidationChecker', functionName: 'cgp-validation-checker', memorySize: 512, timeout: cdk.Duration.minutes(5), roleKey: 'validationChecker' },
      { id: 'ExportHandler', functionName: 'cgp-export-handler', memorySize: 256, timeout: cdk.Duration.minutes(5), roleKey: 'exportHandler' },
      { id: 'MetadataIngestor', functionName: 'cgp-metadata-ingestor', memorySize: 256, timeout: cdk.Duration.seconds(60), roleKey: 'metadataIngestor' },
      { id: 'ReportGenerator', functionName: 'cgp-report-generator', memorySize: 512, timeout: cdk.Duration.minutes(2), roleKey: 'reportGenerator' },
    ];

    this.lambdaFunctions = lambdaConfig.map((config) => {
      return new lambda.Function(this, config.id, {
        functionName: config.functionName,
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: 'handler.handler',
        code: lambda.Code.fromInline('def handler(event, context): pass'),
        memorySize: config.memorySize,
        timeout: config.timeout,
        role: props.lambdaRoles[config.roleKey] as iam.IRole,
        environment: {
          DATA_LAKE_BUCKET: props.dataLakeBucket.bucketName,
          METADATA_TABLE: props.metadataTable.tableName,
        },
      });
    });

    const [
      ingestionTriggerFn,
      qcOrchestratorFn,
      variantCallingFn,
      validationCheckerFn,
      exportHandlerFn,
      metadataIngestorFn,
      reportGeneratorFn,
    ] = this.lambdaFunctions;

    // =========================================================================
    // Step Functions — State Machine Definition
    // =========================================================================

    // Common retry configuration for all states
    const retryConfig: sfn.RetryProps[] = [
      {
        errors: ['States.ALL'],
        maxAttempts: 2,
        interval: cdk.Duration.seconds(5),
        backoffRate: 2.0,
      },
    ];

    // SNS publish task for failure handling
    const notifyFailure = new tasks.SnsPublish(this, 'NotifyFailure', {
      topic: this.snsTopic,
      message: sfn.TaskInput.fromJsonPathAt('$'),
      subject: 'CGP Workflow Failure',
    });

    // HandleFailure state: publishes to SNS then succeeds (terminal)
    const handleFailure = notifyFailure.next(
      new sfn.Pass(this, 'WorkflowFailed', {
        comment: 'Terminal failure state — notification sent',
      }),
    );

    // Common catch configuration for all states
    const catchConfig: sfn.CatchProps = {
      errors: ['States.ALL'],
      resultPath: '$.error',
    };

    // Define LambdaInvoke states for each step
    const triggerIngestion = new tasks.LambdaInvoke(this, 'TriggerIngestion', {
      lambdaFunction: ingestionTriggerFn,
      outputPath: '$.Payload',
      comment: 'Validate FASTQ input and stage for processing',
    });
    triggerIngestion.addRetry(...retryConfig);
    triggerIngestion.addCatch(handleFailure, catchConfig);

    const runQC = new tasks.LambdaInvoke(this, 'RunQC', {
      lambdaFunction: qcOrchestratorFn,
      outputPath: '$.Payload',
      comment: 'Run QC analysis on raw sequencing data',
    });
    runQC.addRetry(...retryConfig);
    runQC.addCatch(handleFailure, catchConfig);

    const runVariantCalling = new tasks.LambdaInvoke(this, 'RunVariantCalling', {
      lambdaFunction: variantCallingFn,
      outputPath: '$.Payload',
      comment: 'Invoke variant caller on aligned data',
    });
    runVariantCalling.addRetry(...retryConfig);
    runVariantCalling.addCatch(handleFailure, catchConfig);

    const validateResults = new tasks.LambdaInvoke(this, 'ValidateResults', {
      lambdaFunction: validationCheckerFn,
      outputPath: '$.Payload',
      comment: 'Compare VCF against truth set for validation',
    });
    validateResults.addRetry(...retryConfig);
    validateResults.addCatch(handleFailure, catchConfig);

    const exportToS3 = new tasks.LambdaInvoke(this, 'ExportToS3', {
      lambdaFunction: exportHandlerFn,
      outputPath: '$.Payload',
      comment: 'Export metrics and provenance to results/',
    });
    exportToS3.addRetry(...retryConfig);
    exportToS3.addCatch(handleFailure, catchConfig);

    const ingestMetadata = new tasks.LambdaInvoke(this, 'IngestMetadata', {
      lambdaFunction: metadataIngestorFn,
      outputPath: '$.Payload',
      comment: 'Write run records to DynamoDB metadata store',
    });
    ingestMetadata.addRetry(...retryConfig);
    ingestMetadata.addCatch(handleFailure, catchConfig);

    const generateReport = new tasks.LambdaInvoke(this, 'GenerateReport', {
      lambdaFunction: reportGeneratorFn,
      outputPath: '$.Payload',
      comment: 'Generate AI-drafted report with guardrails',
    });
    generateReport.addRetry(...retryConfig);
    generateReport.addCatch(handleFailure, catchConfig);

    const workflowComplete = new sfn.Succeed(this, 'WorkflowComplete', {
      comment: 'All pipeline stages completed successfully',
    });

    // Chain the states
    const definition = triggerIngestion
      .next(runQC)
      .next(runVariantCalling)
      .next(validateResults)
      .next(exportToS3)
      .next(ingestMetadata)
      .next(generateReport)
      .next(workflowComplete);

    // Create the state machine
    this.stateMachine = new sfn.StateMachine(this, 'CgpWorkflowStateMachine', {
      stateMachineName: 'cgp-genomics-workflow',
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      stateMachineType: sfn.StateMachineType.STANDARD,
      timeout: cdk.Duration.minutes(60),
      comment: 'Clinical Genomics Platform — end-to-end variant calling workflow',
    });

    // =========================================================================
    // EventBridge Rule — S3 PutObject on raw/*.fastq.gz
    // =========================================================================
    const eventRule = new events.Rule(this, 'FastqUploadRule', {
      ruleName: 'cgp-fastq-upload-trigger',
      description: 'Triggers the genomics workflow when a FASTQ file is uploaded to raw/',
      eventPattern: {
        source: ['aws.s3'],
        detailType: ['Object Created'],
        detail: {
          bucket: {
            name: [props.dataLakeBucket.bucketName],
          },
          object: {
            key: [{ prefix: 'raw/' }, { suffix: '.fastq.gz' }],
          },
        },
      },
    });

    // Target: Start Step Functions execution
    eventRule.addTarget(new targets.SfnStateMachine(this.stateMachine, {
      deadLetterQueue: this.dlqQueue,
      retryAttempts: 3,
    }));

    // =========================================================================
    // Outputs
    // =========================================================================
    new cdk.CfnOutput(this, 'StateMachineArn', {
      value: this.stateMachine.stateMachineArn,
      description: 'ARN of the Step Functions workflow state machine',
      exportName: 'CgpStateMachineArn',
    });

    new cdk.CfnOutput(this, 'SnsTopicArn', {
      value: this.snsTopic.topicArn,
      description: 'ARN of the failure notification SNS topic',
      exportName: 'CgpFailureTopicArn',
    });

    new cdk.CfnOutput(this, 'DlqUrl', {
      value: this.dlqQueue.queueUrl,
      description: 'URL of the EventBridge dead-letter queue',
      exportName: 'CgpEventBridgeDlqUrl',
    });
  }
}
