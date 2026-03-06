# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-03-06

### Added
- **Metrics Endpoint**: Added `/metrics` endpoint to Orchestration service for Prometheus-style monitoring
- **Test Coverage**: Added pytest-cov for coverage reporting with `make test-cov` command
- **Configuration Documentation**: Added comprehensive configuration hierarchy documentation to README

### Changed
- **Error Handling**: Improved error handling in Telegram alerting with specific exception types
- **Makefile**: Fixed demo script path and added migration validation to release checks

### Fixed
- **Test Failures**: Fixed missing `now_utc` parameter in safety drill tests
- **MT5 Bridge Security**: Updated placeholder secret to more secure default
- **Demo Path**: Corrected Makefile to point to actual demo script location

### Security
- Enhanced secret management practices in MT5 bridge configuration

## [1.0.0] - 2026-02-28

### Added
- **Mission A-C**: Research, Calibration, and Hindsight scoring systems.
- **Mission D-E**: Live Data Bridge and Trade Capture integration with MT5.
- **Mission F**: Trade Management Assistant for rule-based SL/TP suggestions.
- **Mission G**: Weekly Tuning Assistant with parameter proposal reports.
- **Mission H**: Pilot Run Protocol and Graduation Gate for 10-session rolling evaluation.
- **Mission I**: Release Pack v1.0, Operator Manual, and Disaster Recovery playbook.
- Dashboard views for all major modules (Ops, Tickets, Queue, Hindsight, Calibration, Tuning, Pilot).
- CLI tools for packet management, report generation, and system validation.

### Changed
- Refactored all inline CSS to external `index.css` for dashboard styling.
- Hardened database schemas with strict constraints and foreign keys.

### Fixed
- Improved quote freshness handling in Live Data Bridge.
- Fixed Postgres/SQLite compatibility issues in the research modules.

### Security
- Implemented dashboard authentication (Username/Password).
- Added kill switch safety mechanisms.
- System-wide guardrails for capital protection and risk management.
