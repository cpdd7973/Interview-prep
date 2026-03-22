# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **ISSUE-001**: Fixed white screen on join and improved reconnection resilience.
- **ISSUE-002**: Fixed AI voice not speaking and candidate audio not capturing on Oracle Cloud.
- **ISSUE-006**: Fixed regression where AI greeting was not heard.
- **ISSUE-007**: Fixed Mic and VAD Status remaining IDLE at start of interview.
- **ISSUE-008**: Fixed Dashboard refreshing loop during form input (HMR fix).
- **ISSUE-009**: Fixed double AI voice playback (overlapping primary and fallback voices).

### Added
- Docker Compose deployment guide.
- Agent Orchestrator and issue tracking infrastructure.
- Diagnostic Mic status indicators (`WAITING`, `CAPTURING`).
