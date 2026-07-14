import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cw from 'aws-cdk-lib/aws-cloudwatch';

interface ObservabilityStackProps extends cdk.StackProps {
  jobQueueName: string;
}

/**
 * CloudWatch log retention + a dashboard/alarm on Batch job failures.
 * Retention is set explicitly (not "never expire") because a defined retention
 * period is itself an accreditation control.
 */
export class ObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);

    new logs.LogGroup(this, 'PipelineLogGroup', {
      logGroupName: '/cgp/pipeline',
      retention: logs.RetentionDays.ONE_YEAR, // defined retention, not indefinite
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const failedJobs = new cw.Metric({
      namespace: 'AWS/Batch',
      metricName: 'FailedJobs',
      dimensionsMap: { JobQueue: props.jobQueueName },
      statistic: 'Sum',
      period: cdk.Duration.hours(1),
    });

    const failureAlarm = new cw.Alarm(this, 'JobFailureAlarm', {
      metric: failedJobs,
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmDescription: 'A pipeline job failed on Batch — investigate before releasing results',
      treatMissingData: cw.TreatMissingData.NOT_BREACHING,
    });

    const dashboard = new cw.Dashboard(this, 'CgpOpsDashboard', {
      dashboardName: 'cgp-pipeline-ops',
    });
    dashboard.addWidgets(
      new cw.GraphWidget({ title: 'Batch failed jobs (1h)', left: [failedJobs], width: 12 }),
      new cw.AlarmWidget({ title: 'Job failure alarm', alarm: failureAlarm, width: 12 }),
    );

    new cdk.CfnOutput(this, 'OpsDashboardName', { value: dashboard.dashboardName ?? 'cgp-pipeline-ops' });
  }
}
