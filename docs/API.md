# JARVIS REST API Documentation

JARVIS exposes a FastAPI REST API when started with `--api` or via `run_api.bat`.

## Endpoints

### 1. `POST /api/command`
Execute a natural language command end-to-end.

**Request Body**:
```json
{
  "text": "what time is it"
}
```

**Response**:
```json
{
  "result": "The time is 11:35 PM, sir.",
  "status": "success"
}
```

### 2. `POST /api/plan`
Generate a structured execution plan dict without executing it.

**Request Body**:
```json
{
  "text": "open chrome and search for weather"
}
```

### 3. `GET /api/health`
Check application & service container status.

**Response**:
```json
{
  "status": "ok",
  "services": {
    "event_bus": {"name": "event_bus", "healthy": true},
    "engine": {"name": "engine", "healthy": true}
  }
}
```

### 4. `GET /api/voice/state`
Get active/passive state of the voice recognition backend.

**Response**:
```json
{
  "active": true,
  "state": "active"
}
```
