import os
import subprocess
from functools import lru_cache


@lru_cache
def get_version() -> str:
    try:
        version_path = os.path.join(os.path.dirname(__file__), "..", "..", "VERSION")
        with open(version_path) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


@lru_cache
def get_git_commit() -> str:
    try:
        # Try to get short hash
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.STDOUT
            )
            .decode("utf-8")
            .strip()
        )
        return commit
    except Exception:
        return "unknown-commit"


def get_system_metadata() -> dict:
    return {
        "version": get_version(),
        "git_commit": get_git_commit(),
        "guardrails_version": "1.0",  # Stubbed, could be read from a config hash
        "policy_hash": "latest",  # Stubbed, could be calculated from active profiles
    }
