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
- ISSUE-006: Fixed regression where microphone remained idle after AI greeting.
    - Implemented `_speakWithSafetyNet` with a hard timeout guard (CORE Rule #7) for browser TTS.
    - Ensured microphone is always unblocked regardless of `speechSynthesis` API behavior.


### Added
- Docker Compose deployment guide.
- Agent Orchestrator and issue tracking infrastructure.
