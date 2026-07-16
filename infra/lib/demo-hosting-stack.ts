import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';

/**
 * Free-tier deployment: single EC2 t2.micro running Docker Compose.
 *
 * Hosts all three services on one instance:
 *  - Streamlit demo on port 8501
 *  - Metabase on port 3000
 *  - Postgres (internal, port 5432 — not exposed publicly)
 *
 * Cost: ~$15/month (t3.small 2 GB RAM needed for Metabase + Streamlit + Postgres).
 * t2.micro (1 GB) is insufficient — Metabase alone needs ~1 GB heap.
 *
 * The instance bootstraps via user-data: installs Docker + Compose, clones
 * the repo, runs `docker compose up -d`. Services auto-restart on reboot.
 *
 * Security: only ports 8501 (Streamlit) and 3000 (Metabase) are open to the
 * internet. SSH (22) is open for debugging — restrict to your IP in production.
 */
export class DemoHostingStack extends cdk.Stack {
  public readonly instancePublicIp: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // =========================================================================
    // VPC — use default VPC (free, no NAT gateway)
    // =========================================================================
    const vpc = ec2.Vpc.fromLookup(this, 'DefaultVpc', { isDefault: true });

    // =========================================================================
    // Security Group — allow Streamlit (8501), Metabase (3000), SSH (22)
    // =========================================================================
    const sg = new ec2.SecurityGroup(this, 'DemoSg', {
      vpc,
      securityGroupName: 'cgp-demo-hosting',
      description: 'Allow public access to Streamlit and Metabase',
      allowAllOutbound: true,
    });

    sg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(8501), 'Streamlit demo');
    sg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(3000), 'Metabase dashboard');
    // SSH removed — use SSM Session Manager instead (IAM role already has AmazonSSMManagedInstanceCore)

    // =========================================================================
    // IAM Role — minimal (SSM for Session Manager access, no SSH key needed)
    // =========================================================================
    const role = new iam.Role(this, 'InstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    // =========================================================================
    // User Data — bootstrap Docker, clone repo, start services
    // =========================================================================
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      '#!/bin/bash',
      'set -euxo pipefail',
      '',
      '# Install Docker',
      'yum update -y',
      'yum install -y docker git',
      'systemctl enable docker',
      'systemctl start docker',
      'usermod -aG docker ec2-user',
      '',
      '# Install Docker Compose (v2 plugin)',
      'mkdir -p /usr/local/lib/docker/cli-plugins',
      'curl -SL "https://github.com/docker/compose/releases/download/v2.29.1/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose',
      'chmod +x /usr/local/lib/docker/cli-plugins/docker-compose',
      '',
      '# Clone the repo and start services',
      'cd /home/ec2-user',
      'git clone https://github.com/qclayssen/clinical-genomics-platform.git app',
      'cd app',
      'docker compose up -d',
      '',
      '# Ensure services restart on reboot',
      'cat > /etc/systemd/system/cgp-demo.service << \'EOF\'',
      '[Unit]',
      'Description=CGP Demo Stack (Docker Compose)',
      'After=docker.service',
      'Requires=docker.service',
      '',
      '[Service]',
      'Type=oneshot',
      'RemainAfterExit=yes',
      'WorkingDirectory=/home/ec2-user/app',
      'ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose up -d',
      'ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose down',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF',
      'systemctl enable cgp-demo.service',
    );

    // =========================================================================
    // EC2 Instance — t2.micro (free tier), Amazon Linux 2023, 20 GB gp3
    // =========================================================================
    const instance = new ec2.Instance(this, 'DemoInstance', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      securityGroup: sg,
      role,
      userData,
      blockDevices: [
        {
          deviceName: '/dev/xvda',
          volume: ec2.BlockDeviceVolume.ebs(20, {
            volumeType: ec2.EbsDeviceVolumeType.GP3,
            encrypted: true,
          }),
        },
      ],
      associatePublicIpAddress: true,
    });

    this.instancePublicIp = instance.instancePublicIp;

    // =========================================================================
    // Outputs
    // =========================================================================
    new cdk.CfnOutput(this, 'StreamlitUrl', {
      value: `http://${instance.instancePublicIp}:8501`,
      description: 'Public URL of the Streamlit demo app',
      exportName: 'CgpStreamlitUrl',
    });

    new cdk.CfnOutput(this, 'MetabaseUrl', {
      value: `http://${instance.instancePublicIp}:3000`,
      description: 'Public URL of the Metabase dashboard',
      exportName: 'CgpMetabaseUrl',
    });

    new cdk.CfnOutput(this, 'SshCommand', {
      value: `ssh ec2-user@${instance.instancePublicIp}`,
      description: 'SSH to the instance (or use SSM Session Manager)',
    });
  }
}
