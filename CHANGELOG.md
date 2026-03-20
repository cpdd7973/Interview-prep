# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- ISSUE-001: Fixed white screen on join and improved reconnection resilience.
- ISSUE-002: Fixed AI voice not speaking and candidate audio not capturing on Oracle Cloud.
    - Added browser-native `speechSynthesis` fallback for TTS.
    - Hardened `MediaRecorder` with MIME type selection.
    - Added diagnostic UI for audio telemetry.
    - Added backend binary reception logging.

### Added
- Docker Compose deployment guide.
- Agent Orchestrator and issue tracking infrastructure.
