#!/bin/bash
# hygiene.sh - TH Trading System Code Hygiene Script (Bash Fallback)
# Automatically fixes safe issues and validates merge-safety gates.

set -e

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

write_header() { echo -e "\n${CYAN}=== $1 ===${NC}"; }
write_success() { echo -e "${GREEN}[PASS] $1${NC}"; }
write_failure() { echo -e "${RED}[FAIL] $1${NC}"; }

BLOCKER_FOUND=0

write_header "PHASE 1: AUTO-FIXING SAFE ISSUES"

echo "Running Ruff Fix..."
python3 -m ruff check --fix . || { write_failure "Ruff fix failed"; BLOCKER_FOUND=1; }
echo "Running Ruff Format..."
python3 -m ruff format . || { write_failure "Ruff format failed"; BLOCKER_FOUND=1; }

if [ $BLOCKER_FOUND -eq 0 ]; then
    write_success "Auto-fixes applied successfully."
fi

write_header "PHASE 2: STRICT VALIDATION"

# 1. Lint Check
echo "Verifying Lint..."
if python3 -m ruff check .; then
    write_success "Lint validation passed."
else
    write_failure "Lint validation failed."
    BLOCKER_FOUND=1
fi

# 2. Type Check
echo "Verifying Type Safety..."
if python3 -m mypy .; then
    write_success "Type validation passed."
else
    write_failure "Type validation failed."
    BLOCKER_FOUND=1
fi

# 3. Test Check
echo "Running Unit Tests..."
if python3 -m pytest; then
    write_success "Tests passed."
else
    write_failure "Tests failed."
    BLOCKER_FOUND=1
fi

write_header "FINAL HYGIENE REPORT"

if [ $BLOCKER_FOUND -ne 0 ]; then
    write_failure "CRITICAL: Code hygiene validation FAILED."
    write_failure "STATUS: [NOT READY FOR MERGE]"
    exit 1
else
    write_success "All hygiene gates PASSED."
    write_success "STATUS: [READY FOR MERGE]"
    exit 0
fi
