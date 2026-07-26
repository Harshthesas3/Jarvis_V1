"""Standard system event types for JARVIS.

Canonical event types used across all layers for inter-component
event-driven communication.
"""

# System lifecycle
SYSTEM_STARTING = "system.starting"
SYSTEM_STARTED = "system.started"
SYSTEM_STOPPING = "system.stopping"
SYSTEM_STOPPED = "system.stopped"
SYSTEM_ERROR = "system.error"
SYSTEM_HEALTH_CHECK = "system.health_check"

# Voice / Speech
WAKE_WORD_DETECTED = "voice.wake_word_detected"
LISTENING_STARTED = "voice.listening_started"
LISTENING_STOPPED = "voice.listening_stopped"
COMMAND_RECEIVED = "voice.command_received"
TRANSCRIPTION_COMPLETE = "voice.transcription_complete"
SPEECH_SYNTHESIS_STARTED = "voice.speech_started"
SPEECH_SYNTHESIS_COMPLETE = "voice.speech_complete"

# Planning / Intent
PLANNING_STARTED = "plan.started"
PLANNING_COMPLETE = "plan.complete"
PLANNING_FAILED = "plan.failed"
INTENT_CLASSIFIED = "plan.intent_classified"
FAST_PATH_HIT = "plan.fast_path_hit"

# Execution
EXECUTION_STARTED = "execution.started"
EXECUTION_COMPLETE = "execution.complete"
EXECUTION_FAILED = "execution.failed"
EXECUTION_CANCELLED = "execution.cancelled"
TASK_STARTED = "execution.task_started"
TASK_COMPLETE = "execution.task_complete"
TASK_FAILED = "execution.task_failed"
TASK_RETRYING = "execution.task_retrying"
GRAPH_VALIDATED = "execution.graph_validated"
GRAPH_INVALID = "execution.graph_invalid"

# Memory
MEMORY_STORED = "memory.stored"
MEMORY_RECALLED = "memory.recalled"
MEMORY_CLEARED = "memory.cleared"
MEMORY_BACKUP_CREATED = "memory.backup_created"

# Plugin
PLUGIN_LOADED = "plugin.loaded"
PLUGIN_UNLOADED = "plugin.unloaded"
PLUGIN_ERROR = "plugin.error"
PLUGIN_HOT_RELOADED = "plugin.hot_reloaded"

# Automation
APP_LAUNCHED = "automation.app_launched"
APP_CLOSED = "automation.app_closed"
WINDOW_FOCUSED = "automation.window_focused"
SEARCH_PERFORMED = "automation.search_performed"
SCREENSHOT_TAKEN = "automation.screenshot_taken"
UI_ACTION_PERFORMED = "automation.ui_action_performed"

# Errors
ERROR_OCCURRED = "error.occurred"
ERROR_RECOVERED = "error.recovered"
ERROR_UNRECOVERABLE = "error.unrecoverable"
