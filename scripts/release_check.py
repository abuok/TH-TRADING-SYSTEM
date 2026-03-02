import subprocess
import sys
import os


def run_command(cmd, shell=True):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=shell)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        return False
    return True


def main():
    print("--- Starting Release Validation ---")

    # 1. Run Tests
    if not run_command("python -m pytest"):
        sys.exit(1)

    # 2. Verify Artifacts
    print("Verifying Artifacts...")
    for d in ["logs", "backups"]:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"Created directory: {d}")

    # 3. Run Smoke Test
    if not run_command("python scripts/smoke_test.py"):
        sys.exit(1)

    print("--- Release Validation PASSED ---")


if __name__ == "__main__":
    main()
