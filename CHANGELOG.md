# Changelog

All notable changes to the JARVIS project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-07-26

### Added
- **Voice-First Architecture**: Continuous active speech mode with passive wake-word monitoring (`"I'm back"` / `"Hey Jarvis"`).
- **FastCommandRouter**: Deterministic regex/keyword routing bypassing LLMs for sub-millisecond execution of desktop/media commands.
- **REST API Server**: FastAPI application server with CORS support and full system state endpoints.
- **Modern HUD Frontend**: Real-time canvas audio visualizer and control panel UI.
- **Automated Setup & Preflight Verification**: Environment checks for Python, Ollama, system audio, and local models.

### Changed
- Refactored DAG execution engine with fallback adapters.
- Thread-safe audio playback and event synchronization.

### Fixed
- Fixed TTS audio playback truncation in API mode.
- Remediated stub handlers in execution adapter.
- Fixed TOCTOU race condition in `wait_for_playback()`.
