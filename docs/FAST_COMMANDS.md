# Fast Command Router Reference

The **FastCommandRouter** provides deterministic, sub-millisecond command execution without invoking an LLM.

## Supported Fast Commands

| Command Category | Sample Voice Input | Trigger Action |
| ---------------- | ------------------ | -------------- |
| **Application Launching** | `"open chrome"`, `"open terminal"`, `"open vs code"` | `open_app` |
| **Volume Control** | `"volume up"`, `"volume down"`, `"mute"`, `"unmute"` | `volume_control` |
| **System Info** | `"what time is it"`, `"what is the date"` | `time`, `date` |
| **System Stats** | `"cpu usage"`, `"ram usage"`, `"battery"` | `system_stats` |
| **Desktop Control** | `"show desktop"`, `"take screenshot"`, `"lock pc"` | `show_desktop`, `screenshot`, `pc_control` |
| **Media Playback** | `"play music"`, `"pause music"`, `"next track"` | `music` |
| **Reminders** | `"remind me to check email in 10 minutes"` | `reminder` |
| **Web Search** | `"search the web for python tutorials"` | `web_search` |

## Performance Impact

- **Keyword Pre-filtering**: Checks input against a set of $O(1)$ lookup strings.
- **Regex Match**: Executes lightweight regex patterns only if keywords match.
- **Execution Time**: $< 2\text{ ms}$ (vs $1,500\text{ ms} - 4,000\text{ ms}$ for LLM planning).
