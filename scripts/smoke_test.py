import os
import sys
import logging
from datetime import datetime

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmokeTest")

def check_directories():
    dirs = ["logs", "backups", "docs", "config"]
    for d in dirs:
        if not os.path.exists(d):
            logger.error(f"Missing directory: {d}")
            return False
        if not os.access(d, os.W_OK):
            logger.error(f"Directory not writable: {d}")
            return False
    logger.info("Directories check passed.")
    return True

def check_files():
    files = ["VERSION", "CHANGELOG.md", "docs/OPERATOR_MANUAL.md", "docs/RELEASE_CHECKLIST.md"]
    for f in files:
        if not os.path.exists(f):
            logger.error(f"Missing file: {f}")
            return False
    logger.info("Files check passed.")
    return True

def check_env():
    # Basic check for environment variables used in the bridge/dashboard
    # In a real smoke test, we'd check if specific keys exist
    logger.info("Environment check passed (simulated).")
    return True

def run_smoke_test():
    logger.info(f"Starting smoke test at {datetime.now()}")
    
    if not check_directories():
        sys.exit(1)
        
    if not check_files():
        sys.exit(1)
        
    if not check_env():
        sys.exit(1)
        
    logger.info("Smoke test COMPLETED SUCCESSFULLY.")

if __name__ == "__main__":
    run_smoke_test()
