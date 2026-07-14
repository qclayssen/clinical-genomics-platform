import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as sns from 'aws-cdk-lib/aws-sns';

export interface ObservabilityStackProps extends cdk.StackProps {
  stateMachine: sfn.IStateMachine;
  lambdaFunctions: lambda.IFunction[];
  dlqQueue: sqs.IQueue;
  snsTopic: sns.ITopic;
}

/**
 * CloudWatch alarms, log groups, and dashboard for the serverless pipeline.
 * Monitors Step Functions executions, Lambda errors, DLQ depth, and billing.
 * All alarms publish to a shared SNS topic for operator notifications.
 */
export class ObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);

    const { stateMachine, lambdaFunctions, dlqQueue, snsTopic } = props;
    const snsAction = new cw_actions.SnsAction(snsTopic);

    // ─── Log Groups ───────────────────────────────────────────────────────────
    // Create a CloudWatch LogGroup per Lambda function with 30-day retention.
    lambdaFunctions.forEach((fn, idx) => {
      new logs.LogGroup(this, `LogGroup-${idx}`, {
        logGroupName: `/aws/lambda/${fn.functionName}`,
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      });
    });

    // ─── Alarm 1: Step Functions Executions Failed ────────────────────────────
    const sfnExecutionsFailed = new cw.Alarm(this, 'SfnExecutionsFailed', {
      alarmDescription: 'Step Functions execution failed — investigate pipeline run',
      metric: stateMachine.metricFailed({
        period: cdk.Duration.minutes(1),
        statistic: 'Sum',
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cw.TreatMissingData.NOT_BREACHING,
    });
    sfnExecutionsFailed.addAlarmAction(snsAction);

    // ─── Alarm 2: Lambda Error Rate > 5% (per function) ──────────────────────
    lambdaFunctions.forEach((fn, idx) => {
      const errors = fn.metricErrors({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      });
      const invocations = fn.metricInvocations({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      });

      const errorRate = new cw.MathExpression({
        expression: '(errors / invocations) * 100',
        usingMetrics: { errors, invocations },
        period: cdk.Duration.minutes(5),
      });

      const alarm = new cw.Alarm(this, `LambdaErrorRate-${idx}`, {
        alarmDescription: `Lambda error rate > 5% over 5 min (function ${idx})`,
        metric: errorRate,
        threshold: 5,
        evaluationPeriods: 1,
        comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
        treatMissingData: cw.TreatMissingData.NOT_BREACHING,
      });
      alarm.addAlarmAction(snsAction);
    });

    // ─── Alarm 3: Step Functions Execution Time Too Long (>30 min) ────────────
    const sfnExecutionTimeTooLong = new cw.Alarm(this, 'SfnExecutionTimeTooLong', {
      alarmDescription: 'Step Functions execution exceeded 30 minutes',
      metric: stateMachine.metricTime({
        period: cdk.Duration.minutes(1),
        statistic: 'Maximum',
      }),
      threshold: 1800000, // 30 minutes in milliseconds
      evaluationPeriods: 1,
      comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cw.TreatMissingData.NOT_BREACHING,
    });
    sfnExecutionTimeTooLong.addAlarmAction(snsAction);

    // ─── Alarm 4: DLQ Messages Visible ────────────────────────────────────────
    const dlqMessagesVisible = new cw.Alarm(this, 'DlqMessagesVisible', {
      alarmDescription: 'Dead-letter queue has unprocessed messages — check failed EventBridge deliveries',
      metric: dlqQueue.metricApproximateNumberOfMessagesVisible({
        period: cdk.Duration.minutes(1),
        statistic: 'Sum',
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cw.TreatMissingData.NOT_BREACHING,
    });
    dlqMessagesVisible.addAlarmAction(snsAction);

    // ─── Alarm 5: Billing Alarm — EstimatedCharges > $1 ──────────────────────
    const billingMetric = new cw.Metric({
      namespace: 'AWS/Billing',
      metricName: 'EstimatedCharges',
      dimensionsMap: { Currency: 'USD' },
      statistic: 'Maximum',
      period: cdk.Duration.hours(6),
    });

    const billingAlarm = new cw.Alarm(this, 'BillingAlarm', {
      alarmDescription: 'AWS estimated charges exceed $1 — check for unexpected usage',
      metric: billingMetric,
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cw.TreatMissingData.NOT_BREACHING,
    });
    billingAlarm.addAlarmAction(snsAction);

    // ─── Dashboard ────────────────────────────────────────────────────────────
    const dashboard = new cw.Dashboard(this, 'CgpOpsDashboard', {
      dashboardName: 'cgp-serverless-ops',
    });

    // Step Functions widget: started, succeeded, failed
    dashboard.addWidgets(
      new cw.GraphWidget({
        title: 'Step Functions Executions',
        left: [
          stateMachine.metricStarted({ period: cdk.Duration.minutes(5) }),
          stateMachine.metricSucceeded({ period: cdk.Duration.minutes(5) }),
          stateMachine.metricFailed({ period: cdk.Duration.minutes(5) }),
        ],
        width: 12,
      }),
    );

    // Lambda invocations and errors
    const lambdaInvocations: cw.IMetric[] = [];
    const lambdaErrors: cw.IMetric[] = [];
    for (const fn of lambdaFunctions) {
      lambdaInvocations.push(
        fn.metricInvocations({ period: cdk.Duration.minutes(5) }),
      );
      lambdaErrors.push(
        fn.metricErrors({ period: cdk.Duration.minutes(5) }),
      );
    }

    dashboard.addWidgets(
      new cw.GraphWidget({
        title: 'Lambda Invocations',
        left: lambdaInvocations,
        width: 12,
      }),
      new cw.GraphWidget({
        title: 'Lambda Errors',
        left: lambdaErrors,
        width: 12,
      }),
    );

    // DLQ depth
    dashboard.addWidgets(
      new cw.GraphWidget({
        title: 'DLQ Depth',
        left: [
          dlqQueue.metricApproximateNumberOfMessagesVisible({
            period: cdk.Duration.minutes(5),
          }),
        ],
        width: 12,
      }),
    );

    // ─── Outputs ──────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'OpsDashboardName', {
      value: dashboard.dashboardName ?? 'cgp-serverless-ops',
    });
  }
}
