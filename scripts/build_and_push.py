#!/usr/bin/env python3
"""
Build the URL shortener image, push it to ECR, and trigger an ECS rolling deployment.

Run from repo root:
    python scripts/build_and_push.py [--tag latest] [--no-deploy]
"""
import argparse
import base64
import subprocess
import sys

import boto3

REGION = "ap-southeast-2"


def ssm_get(name):
    return boto3.client("ssm", region_name=REGION).get_parameter(Name=name)["Parameter"]["Value"]


def run(cmd, **kwargs):
    print(f"+ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def ecr_login(ecr_uri):
    ecr = boto3.client("ecr", region_name=REGION)
    token = ecr.get_authorization_token()
    auth_data = token["authorizationData"][0]
    user, password = base64.b64decode(auth_data["authorizationToken"]).decode().split(":", 1)
    registry = auth_data["proxyEndpoint"]
    run(
        ["docker", "login", "--username", user, "--password-stdin", registry],
        input=password.encode(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="latest", help="Image tag (default: latest)")
    parser.add_argument("--no-deploy", action="store_true", help="Push only, skip ECS deployment")
    args = parser.parse_args()

    ecr_uri = ssm_get("/ops-lab/fargate/ecr-repo-uri")
    image   = f"{ecr_uri}:{args.tag}"

    ecr_login(ecr_uri)
    run(["docker", "build", "-t", image, "."])
    run(["docker", "push", image])
    print(f"\nPushed: {image}")

    if args.no_deploy:
        return

    cluster = ssm_get("/ops-lab/fargate/cluster-name")
    service = ssm_get("/ops-lab/fargate/service-name")
    boto3.client("ecs", region_name=REGION).update_service(
        cluster=cluster, service=service, force_new_deployment=True
    )
    print(f"Deployment triggered on {service} — monitor with:")
    print(f"  aws ecs wait services-stable --cluster {cluster} --services {service}")


if __name__ == "__main__":
    main()
