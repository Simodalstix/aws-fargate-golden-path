#!/usr/bin/env python3
"""
Verify Fargate stack health: SSM outputs, ECS service state, ALB endpoints,
and a URL shortener smoke test.

    python scripts/verify_fargate.py
"""
import json
import sys
import urllib.error
import urllib.request

import boto3

REGION = "ap-southeast-2"

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

SSM_PARAMS = [
    "/ops-lab/fargate/cluster-name",
    "/ops-lab/fargate/service-name",
    "/ops-lab/fargate/alb-dns-name",
    "/ops-lab/fargate/ecr-repo-uri",
    "/ops-lab/fargate/task-definition-arn",
]


def ok(msg):      print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg):    print(f"  {RED}✗{RESET}  {msg}")
def warn(msg):    print(f"  {YELLOW}!{RESET}  {msg}")
def section(msg): print(f"\n{BOLD}{msg}{RESET}")


def main():
    ssm = boto3.client("ssm",  region_name=REGION)
    ecs = boto3.client("ecs",  region_name=REGION)
    failures = 0

    # ── SSM outputs ───────────────────────────────────────────────────────────
    section("SSM Parameters")
    params = {}
    for name in SSM_PARAMS:
        try:
            params[name] = ssm.get_parameter(Name=name)["Parameter"]["Value"]
            ok(f"{name}  =  {params[name][:80]}")
        except Exception as exc:
            fail(f"{name}  —  {exc}")
            failures += 1

    if failures:
        print(f"\n{RED}Aborting — SSM parameters missing. Have the stacks been deployed?{RESET}")
        sys.exit(1)

    cluster = params["/ops-lab/fargate/cluster-name"]
    service = params["/ops-lab/fargate/service-name"]
    alb     = params["/ops-lab/fargate/alb-dns-name"]

    # ── ECS service ───────────────────────────────────────────────────────────
    section("ECS Service")
    try:
        svc      = ecs.describe_services(cluster=cluster, services=[service])["services"][0]
        desired  = svc["desiredCount"]
        running  = svc["runningCount"]
        pending  = svc["pendingCount"]
        status   = svc["status"]

        (ok if status == "ACTIVE" else fail)(f"Status: {status}")
        if status != "ACTIVE":
            failures += 1

        msg = f"Tasks: {running}/{desired} running"
        if pending:
            msg += f"  ({pending} pending)"
        (ok if running == desired else warn)(msg)
        if running != desired:
            failures += 1

        primary = next((d for d in svc["deployments"] if d["status"] == "PRIMARY"), None)
        if primary:
            rollout = primary.get("rolloutState", "UNKNOWN")
            (ok if rollout == "COMPLETED" else warn)(f"Deployment rollout: {rollout}")
    except Exception as exc:
        fail(str(exc))
        failures += 1

    # ── ALB endpoints ─────────────────────────────────────────────────────────
    section("ALB Endpoints")

    for path, label in [("/healthz", "GET /healthz"), ("/", "GET /")]:
        url = f"http://{alb}{path}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = resp.read().decode()
                ok(f"{label}  —  HTTP {resp.status}  {body[:60]}")
        except urllib.error.HTTPError as exc:
            fail(f"{label}  —  HTTP {exc.code}")
            failures += 1
        except Exception as exc:
            fail(f"{label}  —  {exc}")
            failures += 1

    # ── URL shortener smoke test ───────────────────────────────────────────────
    section("URL Shortener Smoke Test")
    try:
        payload = json.dumps({"url": "https://aws.amazon.com"}).encode()
        req = urllib.request.Request(
            f"http://{alb}/shorten",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            code = body.get("code", "")
            ok(f"POST /shorten  —  HTTP {resp.status}  code={code}")
    except urllib.error.HTTPError as exc:
        fail(f"POST /shorten  —  HTTP {exc.code}")
        failures += 1
        code = None
    except Exception as exc:
        fail(f"POST /shorten  —  {exc}")
        failures += 1
        code = None

    if code:
        try:
            # urllib follows redirects; a 200 from aws.amazon.com means the redirect worked
            with urllib.request.urlopen(f"http://{alb}/{code}", timeout=10) as resp:
                ok(f"GET /{code}  —  redirect followed  final HTTP {resp.status}")
        except Exception as exc:
            warn(f"GET /{code}  —  {exc}  (redirect may still be correct)")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if failures:
        print(f"{RED}{BOLD}FAILED — {failures} check(s) did not pass{RESET}")
        sys.exit(1)
    print(f"{GREEN}{BOLD}ALL CHECKS PASSED{RESET}")


if __name__ == "__main__":
    main()
