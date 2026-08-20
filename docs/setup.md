# Setup Guide

This guide walks you through setting up the AI-Powered AWS Self-Healing Security Agent from scratch.

---

## Prerequisites

Before you begin, make sure you have the following:

- An AWS account with Free Tier or credits
- A Telegram bot token (create one via BotFather on Telegram)
- Your Telegram chat ID

---

## Step 1 - Launch an EC2 Instance

1. Go to the AWS EC2 console and click Launch Instance
2. Choose Ubuntu 24.04 LTS as the AMI
3. Select t3.micro as the instance type (free tier eligible)
4. Create or select an existing key pair for SSH access
5. Under security groups, allow SSH (port 22) inbound
6. Launch the instance and note down the instance ID

---

## Step 2 - Create an IAM Role for EC2

The EC2 instance needs permission to communicate with AWS Systems Manager.

1. Go to IAM and click Create role
2. Select AWS service as the trusted entity and choose EC2 as the use case
3. Search for and attach the AmazonSSMManagedInstanceCore policy
4. Name the role ec2-ssm-role and create it
5. Go back to EC2, select your instance, click Actions > Security > Modify IAM role
6. Select ec2-ssm-role and click Update IAM role

---

## Step 3 - Install and Verify SSM Agent on EC2

SSH into your instance and run:

```bash
sudo snap install amazon-ssm-agent --classic
sudo systemctl enable amazon-ssm-agent
sudo systemctl start amazon-ssm-agent
```

Verify it is running:

```bash
sudo snap services amazon-ssm-agent
```

---

## Step 4 - Enable Detailed Monitoring on EC2

1. Select your EC2 instance in the console
2. Go to Actions > Monitor and troubleshoot > Enable detailed monitoring
3. This makes CloudWatch collect CPU data every 1 minute instead of every 5 minutes

---

## Step 5 - Create a CloudWatch Alarm

1. Go to CloudWatch and click Create alarm
2. Select EC2 as the metric source and choose CPUUtilization for your instance
3. Set the threshold to greater than 70 percent
4. Set the period to 1 minute
5. Under notification, create a new SNS topic called cpu-alarm-topic
6. Add your email address as a subscriber and confirm the subscription from your inbox

---

## Step 6 - Create the Lambda Function

1. Go to AWS Lambda and click Create function
2. Choose Author from scratch
3. Name the function infra-healing-agent
4. Select Python 3.13 as the runtime
5. Click Create function
6. Paste the code from lambda/handler.py into the inline editor
7. Click Deploy

---

## Step 7 - Add IAM Permissions to Lambda

The Lambda function needs permission to call Bedrock, SSM, and EC2.

1. Go to your Lambda function and click the Configuration tab
2. Click Permissions and then click the role name to open IAM
3. Click Add permissions then Attach policies
4. Add the following policies:
   - AmazonBedrockFullAccess
   - AmazonSSMFullAccess
   - AmazonEC2FullAccess
5. Save the changes

---

## Step 8 - Add Environment Variables to Lambda

1. Go to your Lambda function and click the Configuration tab
2. Click Environment variables and then Edit
3. Add the following variables:

| Key | Value |
|---|---|
| BOT_TOKEN | Your Telegram bot token |
| CHAT_ID | Your Telegram chat ID |
| INSTANCE_ID | Your EC2 instance ID (e.g. i-0a1b2c3d4e5f) |

---

## Step 9 - Subscribe Lambda to SNS

1. In your Lambda function click Add trigger
2. Select SNS as the source
3. Choose the cpu-alarm-topic you created earlier
4. Click Add

---

## Step 10 - Test the Pipeline

SSH into your EC2 instance and install the stress tool:

```bash
sudo apt update && sudo apt install stress -y
```

**Test MALICIOUS detection:**

Create a file named `miner.py` with an infinite loop inside it, then run two instances to saturate both vCPUs:

```bash
python3 miner.py &
python3 miner.py &
```

**Test LEGITIMATE detection:**

Create a file named `flask_server.py` with an infinite loop inside it, then run two instances:

```bash
python3 flask_server.py &
python3 flask_server.py &
```

**Test UNKNOWN detection:**

Create a file named `worker.py` with an infinite loop inside it, then run two instances:

```bash
python3 worker.py &
python3 worker.py &
```

Within a minute or two you should receive a Telegram message from your bot with the alarm details, Claude's decision, and the action taken.

To stop all test processes after testing:

```bash
kill $(pgrep -f "miner.py|flask_server.py|worker.py")
```

