# Contribution Guide

## Code of Conduct

- Be respectful and constructive
- Focus on what is best for the project
- Maintain professionalism in all communications

## Getting Started

1. Fork the repository
2. Clone your fork
3. Set up the development environment (see [Developer Guide](DEVELOPER_GUIDE.md))
4. Create a feature branch: `git checkout -b feature/my-feature`
5. Make your changes
6. Run tests: `python -m pytest test_*.py -v`
7. Commit and push
8. Open a pull request

## Contribution Types

### Bug Reports

When reporting bugs, include:
- Full error message and stack trace
- Steps to reproduce
- Expected vs actual behavior
- Environment details (Python version, Windows version, model versions)
- `config.json` contents (redact personal paths)

### Feature Requests

Describe the feature with:
- Clear use case
- Expected behavior
- How it fits into the existing architecture
- Implementation approach (if known)

### Code Contributions

#### What We Look For

- Clean, readable code that follows existing patterns
- Proper error handling (return TTS strings, never raise into user-facing paths)
- Appropriate logging
- Tests for new functionality
- Documentation updates
- Backward compatibility maintained

#### What to Avoid

- Hardcoded user-specific paths
- Broad `except Exception` without logging
- Synchronous blocking calls on the main thread (prefer background threads)
- New dependencies without justification
- Breaking existing API contracts

## Coding Standards

### Style

- Follow PEP 8
- Maximum line length: 120 characters
- Use type hints on all public functions
- Module-level docstring for every module
- Public API documented in module docstring

### Patterns

**Handler pattern** (task_executor):
```python
def _handle_action(plan: dict, ctx: ExecutorContext) -> str:
    """Brief description."""
    param = (plan.get("param") or "").strip()
    if not param:
        return "Meaningful error message, sir."
    try:
        # Implementation
        return "Success message, sir."
    except Exception as exc:
        logger.exception("Context")
        return f"Meaningful error, sir. {exc}"
```

**Return dict pattern** (utilities):
```python
def my_function(param: str) -> dict:
    """Brief description."""
    return {
        "ok": True,
        "tts": "Response text, sir.",
        "data": {...},
    }
```

**Plugin pattern**:
```python
from plugins import Plugin, PluginMetadata

class MyPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="MyPlugin",
            version="1.0.0",
            description="Description",
            author="You",
            permissions=[],  # Declare required permissions
        )

PluginClass = MyPlugin
```

### Testing Standards

- Unit tests for planner regex patterns
- Handler tests with mocked context
- Integration tests for multi-step scenarios
- Test edge cases: empty input, missing parameters, invalid formats
- Tests should not require external services (Ollama, network)

## Pull Request Process

1. Ensure all tests pass
2. Update relevant documentation
3. Add a clear PR description explaining the change
4. Reference any related issues
5. Request review from maintainers

### PR Checklist

- [ ] Code follows existing patterns and conventions
- [ ] Tests added/updated and passing
- [ ] Documentation updated (if applicable)
- [ ] No hardcoded paths or user-specific values
- [ ] Error handling follows the project pattern
- [ ] Logging added where appropriate
- [ ] Backward compatibility maintained
- [ ] No unnecessary dependencies added

## Development Workflow

### Adding a Feature

1. Start with an issue describing the feature
2. Discuss architecture approach with maintainers
3. Implement the feature following existing patterns
4. Add a regex pattern in `planner.py` (for new commands)
5. Add the action to `SUPPORTED_ACTIONS`
6. Implement the handler in `task_executor.py`
7. Register in `HANDLERS` dict
8. Add tests
9. Update documentation

### Fixing a Bug

1. Reproduce the bug
2. Identify the root cause
3. Write a test that fails
4. Fix the bug
5. Verify the test passes
6. Ensure existing tests still pass

## Communication

- Use issues for bug reports and feature requests
- Use pull requests for code changes
- Be patient — this is a volunteer-driven project

## Project Governance

- Maintainers review and merge all pull requests
- Breaking changes require discussion and consensus
- The architecture document (ARCHITECTURE.md) is the source of truth for design decisions
