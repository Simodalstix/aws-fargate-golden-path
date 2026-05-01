#!/usr/bin/env python3
"""
Drop into a running Fargate task via ECS Exec (no SSH, no bastion).

Requires the AWS Session Manager plugin:
  https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

Usage:
    python scripts/exec_task.py [--task <id>] [--container app] [--command /bin/sh]
"""
import argparse
import subprocess
import sys

import boto3

REGION = "ap-southeast-2"


def ssm_get(name):
    return boto3.client("ssm", region_name=REGION).get_parameter(Name=name)["Parameter"]["Value"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task",      help="Task ID or ARN (default: first RUNNING task)")
    parser.add_argument("--container", default="app",    help="Container name (default: app)")
    parser.add_argument("--command",   default="/bin/sh", help="Command to run (default: /bin/sh)")
    args = parser.parse_args()

    cluster = ssm_get("/ops-lab/fargate/cluster-name")
    ecs     = boto3.client("ecs", region_name=REGION)

    task_id = args.task
    if not task_id:
        arns = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING")["taskArns"]
        if not arns:
            print("No RUNNING tasks found in cluster.")
            sys.exit(1)
        task_id = arns[0]
        print(f"Targeting task: {task_id.split('/')[-1]}\n")

    cmd = [
        "aws", "ecs", "execute-command",
        "--region",    REGION,
        "--cluster",   cluster,
        "--task",      task_id,
        "--container", args.container,
        "--interactive",
        "--command",   args.command,
    ]

    print(f"+ {' '.join(cmd)}\n")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
