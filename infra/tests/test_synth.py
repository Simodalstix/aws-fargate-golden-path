"""
CDK synthesis smoke test.

Requires AWS credentials and the ops-lab networking + observability stacks
to be deployed (SSM lookups need real values).

    cd infra && python -m pytest tests/test_synth.py -v
"""
import os
import shutil
import subprocess

import pytest

INFRA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def require_cdk():
    if not shutil.which("cdk"):
        pytest.skip("CDK CLI not installed")


def _synth_env():
    env = os.environ.copy()
    env.setdefault("CDK_DEFAULT_ACCOUNT", "820242933814")
    env.setdefault("CDK_DEFAULT_REGION", "ap-southeast-2")
    return env


def test_all_stacks_synthesize():
    result = subprocess.run(
        ["cdk", "synth", "--all"],
        cwd=INFRA_DIR,
        env=_synth_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"cdk synth failed:\n{result.stderr}"


def test_fis_stack_synthesizes():
    result = subprocess.run(
        ["cdk", "synth", "FargateFIS-lab", "-c", "enableFIS=true"],
        cwd=INFRA_DIR,
        env=_synth_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"FIS stack synth failed:\n{result.stderr}"
