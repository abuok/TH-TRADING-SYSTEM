# hygiene.ps1 - TH Trading System Code Hygiene Script
# Automatically fixes safe issues and validates merge-safety gates.

$ErrorActionPreference = "Continue" # Don't stop on warnings to stderr

function Write-Header($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function Write-Success($msg) {
    Write-Host "[PASS] $msg" -ForegroundColor Green
}

function Write-Failure($msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
}

$Global:BlockerFound = $false

Write-Header "PHASE 1: AUTO-FIXING SAFE ISSUES"

Write-Host "Running Ruff Fix..."
python -m ruff check --fix .
if ($LASTEXITCODE -gt 0 -and $LASTEXITCODE -ne 1) { 
    # Exit code 1 just means lint errors found/fixed, which is fine in Phase 1
    # Higher exit codes might mean config errors
    Write-Failure "Ruff fix encountered a configuration or system error (Exit: $LASTEXITCODE)."
    $Global:BlockerFound = $true
}

Write-Host "Running Ruff Format..."
python -m ruff format .
if ($LASTEXITCODE -ne 0) {
    Write-Failure "Ruff format failed."
    $Global:BlockerFound = $true
}

Write-Header "PHASE 2: STRICT VALIDATION"

# 1. Lint Check
Write-Host "Verifying Lint..."
$lintOutput = python -m ruff check . 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "Lint validation passed."
} else {
    Write-Failure "Lint validation failed."
    $lintOutput | Write-Host -ForegroundColor Yellow
    $Global:BlockerFound = $true
}

# 2. Type Check
Write-Host "Verifying Type Safety..."
$typeOutput = python -m mypy . 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "Type validation passed."
} else {
    Write-Failure "Type validation failed."
    $typeOutput | Write-Host -ForegroundColor Yellow
    $Global:BlockerFound = $true
}

# 3. Test Check
Write-Host "Running Unit Tests..."
$testOutput = python -m pytest 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "Tests passed."
} else {
    Write-Failure "Tests failed."
    $testOutput | Select-Object -Last 5 | Write-Host -ForegroundColor Yellow
    $Global:BlockerFound = $true
}

Write-Header "FINAL HYGIENE REPORT"

if ($Global:BlockerFound) {
    Write-Failure "CRITICAL: Code hygiene validation FAILED. See above for details."
    Write-Failure "STATUS: [NOT READY FOR MERGE]"
    exit 1
} else {
    Write-Success "All hygiene gates PASSED."
    Write-Success "STATUS: [READY FOR MERGE]"
    exit 0
}
