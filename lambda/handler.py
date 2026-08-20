import json
import boto3
import urllib.request
import time
import os


# Environment variables
TELEGRAM_BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["CHAT_ID"]
INSTANCE_ID = os.environ["INSTANCE_ID"]


# AWS clients
bedrock_client = boto3.client("bedrock-runtime")
ssm_client = boto3.client("ssm")


def send_telegram_message(message):
    """Send a notification to Telegram."""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    urllib.request.urlopen(request)


def run_ssm_command(command):
    """Run a shell command on EC2 through AWS Systems Manager."""

    response = ssm_client.send_command(
        InstanceIds=[INSTANCE_ID],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [command]
        }
    )

    command_id = response["Command"]["CommandId"]

    # Wait for SSM command to complete.
    for _ in range(15):
        time.sleep(2)

        result = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=INSTANCE_ID
        )

        if result["Status"] in [
            "Success",
            "Failed",
            "Cancelled",
            "TimedOut"
        ]:
            return {
                "status": result["Status"],
                "stdout": result.get("StandardOutputContent", ""),
                "stderr": result.get("StandardErrorContent", "")
            }

    return {
        "status": "Timeout",
        "stdout": "",
        "stderr": "SSM command did not finish within the expected time."
    }


def ask_claude(alarm_name, alarm_reason, process_output):
    """Ask Claude to analyze the CPU-consuming processes."""

    prompt = f"""You are an AWS infrastructure monitoring and healing agent.

A CloudWatch CPU alarm has fired.

Alarm name:
{alarm_name}

Alarm reason:
{alarm_reason}

The infrastructure agent automatically investigated the EC2 instance using:

ps aux --sort=-%cpu | head -10

Output:

{process_output}

Analyze the processes carefully.

LEGITIMATE:
The process is clearly identifiable as normal or harmless or expected workload or application.
Take no action.

MALICIOUS:
There are concrete indicators that the process may be malicious or unauthorized,
such as a suspicious executable name, unusual location, cryptocurrency-mining
behavior, an obviously malicious command, or other clearly abnormal
characteristics.

If multiple processes are suspicious, include all of their PIDs.

UNKNOWN:
The process is consuming high CPU, but there is not enough evidence to determine
whether it is legitimate or malicious.
Do not take any action. A human should be notified.



DECISION RULE:

ONLY and Only choose LEGITIMATE or MALICIOUS when you are 100% certain based
only on the name of the process.

The server is mostly used for running servers, backends, chatbots so they are all LEGITMATE

If there is ANY uncertainty whatsoever, choose UNKNOWN.

UNKNOWN is the default and safest classification.

Never make assumptions about what is normal for this server.
Never infer intent from CPU usage.
Never speculate about possible malicious activity.

Your reasoning MUST describe only observable evidence.

Example:
python normal infinite loop - UNKNOWN because it could be by a user to stress test
miner-virus - MALICIOUS because it looks like a cryptocurrency miner
python whatsapp.py backend - LEGITIMATE because it looks like a WhatsApp bot backend


Reply ONLY with valid JSON in exactly this format:

{{
    "action": "LEGITIMATE | MALICIOUS | UNKNOWN",
    "reason": "Explain your conclusion.",
    "process_ids": [0000]
}}

For LEGITIMATE or UNKNOWN, return an empty array:

{{
    "action": "LEGITIMATE",
    "reason": "Explanation",
    "process_ids": []
}}
"""

    response = bedrock_client.invoke_model(
        modelId="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
    )

    response_body = json.loads(response["body"].read())

    haiku_reply = response_body["content"][0]["text"]

    print(f"Haiku raw response: {repr(haiku_reply)}")

    haiku_reply = haiku_reply.strip()

    if haiku_reply.startswith("```"):
        haiku_reply = haiku_reply.replace("```json", "", 1)
        haiku_reply = haiku_reply.replace("```", "", 1)
        haiku_reply = haiku_reply.strip()

    try:
        return json.loads(haiku_reply)

    except json.JSONDecodeError:
        print(f"Invalid JSON from Haiku: {repr(haiku_reply)}")
        raise


def lambda_handler(event, context):
    """Main Lambda handler triggered by SNS."""

    # ---------------------------------------------------------
    # STEP 1: Get CloudWatch alarm from SNS
    # ---------------------------------------------------------

    sns_record = event["Records"][0]["Sns"]
    alarm_data = json.loads(sns_record["Message"])

    alarm_name = alarm_data["AlarmName"]
    alarm_state = alarm_data["NewStateValue"]
    alarm_reason = alarm_data["NewStateReason"]

    print(f"Alarm: {alarm_name}")
    print(f"State: {alarm_state}")
    print(f"Reason: {alarm_reason}")

    # Only process active alarms.
    if alarm_state != "ALARM":

        print("Alarm is not active. Skipping.")

        return {
            "statusCode": 200,
            "body": "Alarm is not active."
        }

    # ---------------------------------------------------------
    # STEP 2: Automatically investigate the EC2 instance
    # ---------------------------------------------------------

    investigation_command = (
        "ps aux --sort=-%cpu "
        "| grep -v -E 'ssm|amazon-ssm|grep' "
        "| head -10"
    )

    print(f"Running SSM command: {investigation_command}")

    process_result = run_ssm_command(investigation_command)

    print(f"SSM status: {process_result['status']}")
    print(f"Process output:\n{process_result['stdout']}")

    if process_result["status"] != "Success":

        send_telegram_message(
            f"""⚠️ Infrastructure Investigation Failed

Alarm: {alarm_name}

SSM Error:
{process_result["stderr"]}"""
        )

        return {
            "statusCode": 500,
            "body": "SSM investigation failed."
        }

    # ---------------------------------------------------------
    # STEP 3: Give the investigation results to Claude
    # ---------------------------------------------------------

    print("Sending investigation results to Claude...")

    decision = ask_claude(
        alarm_name,
        alarm_reason,
        process_result["stdout"]
    )

    action = decision["action"]
    reason = decision["reason"]
    process_ids = decision.get("process_ids", [])

    print(f"Claude decision: {action}")
    print(f"Claude reasoning: {reason}")
    print(f"Process IDs: {process_ids}")

    # ---------------------------------------------------------
    # STEP 4: Take action based on Claude's decision
    # ---------------------------------------------------------

    remediation_result = "No action taken."

    if action == "MALICIOUS":

        if not process_ids:

            remediation_result = (
                "Claude classified the processes as suspicious "
                "but did not provide any process IDs."
            )

        else:

            print(f"Terminating suspicious processes: {process_ids}")

            valid_process_ids = []

            for pid in process_ids:
                try:
                    valid_process_ids.append(str(int(pid)))
                except (ValueError, TypeError):
                    print(f"Ignoring invalid PID: {pid}")

            if not valid_process_ids:

                remediation_result = (
                    "No valid process IDs were provided by Claude."
                )

            else:

                kill_command = "kill " + " ".join(valid_process_ids)

                print(f"Running SSM command: {kill_command}")

                kill_result = run_ssm_command(kill_command)

                if kill_result["status"] == "Success":

                    remediation_result = (
                        f"Terminated process(es): "
                        f"{', '.join(valid_process_ids)}"
                    )

                else:

                    remediation_result = (
                        f"Failed to terminate process(es): "
                        f"{', '.join(valid_process_ids)}"
                    )

                print(f"Termination result: {kill_result}")

    elif action == "LEGITIMATE":
        remediation_result = "No action taken."

    elif action == "UNKNOWN":
        remediation_result = "No action taken. Human review required."

    else:
        remediation_result = f"Unknown action returned by Claude: {action}"

    # ---------------------------------------------------------
    # STEP 5: Format top 5 processes for Telegram
    # ---------------------------------------------------------

    process_lines = []

    process_output_lines = process_result["stdout"].strip().splitlines()

    # Skip the ps header
    for line in process_output_lines[1:6]:

        parts = line.split(None, 10)

        if len(parts) >= 11:

            pid = parts[1]
            cpu = parts[2]
            command = parts[10]

            # Show only the executable name for cleaner output.
            command_name = command.split("/")[-1].split()[0].rstrip(":")

            process_lines.append(
                f"{len(process_lines) + 1}. "
                f"{command_name} — PID {pid} — CPU {cpu}%"
            )

    top_processes = "\n".join(process_lines)

    # ---------------------------------------------------------
    # STEP 6: Extract CPU percentage from alarm reason
    # ---------------------------------------------------------

    import re

    cpu_match = re.search(r"\[([0-9.]+)", alarm_reason)

    if cpu_match:
        cpu_usage = f"{float(cpu_match.group(1)):.0f}"
    else:
        cpu_usage = "Unknown"

    # ---------------------------------------------------------
    # STEP 7: Send clean Telegram notification
    # ---------------------------------------------------------

    telegram_message = f"""🚨 Infrastructure Alert

Alarm: {alarm_name}
CPU: {cpu_usage}%

AI Assessment: {action}

Reason:
{reason}

Top Processes:
{top_processes}

Action:
{remediation_result}
"""

    send_telegram_message(telegram_message)

    print("Telegram notification sent.")

    # ---------------------------------------------------------
    # STEP 8: Return summary
    # ---------------------------------------------------------

    return {
        "statusCode": 200,
        "body": json.dumps({
            "alarm": alarm_name,
            "ai_action": action,
            "ai_reason": reason,
            "process_ids": process_ids,
            "remediation": remediation_result
        })
    }
