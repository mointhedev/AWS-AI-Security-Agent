# AI-Powered AWS Self-Healing Security Agent

An autonomous AWS security agent that monitors EC2 infrastructure in real time, investigates suspicious activity using AWS Systems Manager, and uses Claude AI on Amazon Bedrock to make intelligent remediation decisions. Sends instant Telegram notifications with the full incident report.

---

## What It Does

When CPU on a monitored EC2 instance spikes above a defined threshold, the agent automatically:

1. Detects the anomaly via CloudWatch
2. Investigates the live process list on the EC2 instance using AWS Systems Manager, without SSH or stored keys
3. Sends the process data to Claude Haiku 4.5 on Amazon Bedrock for analysis
4. Claude classifies the situation into one of three states:
   - LEGITIMATE: Normal workload detected. No action taken. Telegram notification sent.
   - MALICIOUS: Unauthorized or suspicious process detected. Agent kills the process automatically via SSM and sends a Telegram alert.
   - UNKNOWN: Insufficient evidence to act. Human is notified via Telegram to review.

---

## Architecture

EC2 Instance
↓
Amazon CloudWatch (CPU alarm)
↓
Amazon SNS
↓
AWS Lambda
↓
AWS Systems Manager (process investigation)
↓
Amazon Bedrock — Claude Haiku 4.5 (AI decision)
↓
LEGITIMATE → No action
MALICIOUS → SSM kills process + Telegram alert
UNKNOWN → Telegram alert for human review

---

## Real Test Results

**Test 1 — MALICIOUS**
Two miner.py processes consuming 99.9% CPU each. Claude identified the filename as a concrete indicator of cryptocurrency mining activity and Lambda terminated both processes automatically.

**Test 2 — LEGITIMATE**
Two flask_server.py processes at 99.9% CPU. Claude recognized Flask as a legitimate web framework consistent with expected server workload and took no action.

**Test 3 — UNKNOWN**
Two worker.py processes at 99.9% CPU. Claude could not determine whether this was a legitimate backend worker or a runaway process and flagged it for human review.

---

## Tech Stack

- AWS Lambda
- Amazon CloudWatch
- Amazon SNS
- AWS EC2
- AWS Systems Manager (SSM)
- Amazon Bedrock
- Claude Haiku 4.5
- Python 3.13
- Telegram Bot API

---

## Environment Variables

Configure these in your Lambda function under Configuration > Environment variables:

| Variable | Description |
|---|---|
| BOT_TOKEN | Your Telegram bot token from BotFather |
| CHAT_ID | Your Telegram chat ID |
| INSTANCE_ID | The EC2 instance ID to monitor |

---

## Setup

See [docs/setup.md](docs/setup.md) for full step by step setup instructions.

---

## Project Structure

```
self-healing-aws-agent/
├── README.md
├── lambda/
│   └── handler.py
├── architecture/
│   └── diagram.png
└── docs/
    └── setup.md
```
