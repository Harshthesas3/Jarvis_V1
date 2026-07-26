"""
test_executor_validation.py
----------------------------
Executor dry-run validation — registration only, no live dispatch.
Verifies every handler can be registered and the registry is complete.
"""

import logging
logging.disable(logging.CRITICAL)

from planner import SUPPORTED_ACTIONS, register_tool, _TOOL_REGISTRY
from task_executor import register_default_handlers, HANDLERS

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


print("=" * 60)
print("EXECUTOR DRY-RUN VALIDATION")
print("=" * 60)

# 1. Check every SUPPORTED_ACTIONS has a handler
print("\n--- Handler completeness ---")
for action in sorted(SUPPORTED_ACTIONS):
    check(f"'{action}' handler defined", action in HANDLERS,
          f"Missing from HANDLERS")

# 2. Check no extra handlers
for action in sorted(HANDLERS):
    check(f"'{action}' in SUPPORTED_ACTIONS", action in SUPPORTED_ACTIONS,
          f"Extra handler")

print(f"\n  Handlers: {len(HANDLERS)}, Actions: {len(SUPPORTED_ACTIONS)}")

# 3. Registration does not raise
print("\n--- Registration ---")
try:
    register_default_handlers()
    check("register_default_handlers()", True)
except Exception as e:
    check(f"register_default_handlers()", False, str(e))

# 4. Every action now registered in planner
print("\n--- Planner registry ---")
for action in sorted(SUPPORTED_ACTIONS):
    check(f"'{action}' in _TOOL_REGISTRY", action in _TOOL_REGISTRY,
          f"Missing after register_default_handlers()")

# 5. Verify registry has all actions
registered = set(_TOOL_REGISTRY.keys())
expected = SUPPORTED_ACTIONS - {"ai_chat"}
check(f"All {len(SUPPORTED_ACTIONS)} actions registered",
      registered == SUPPORTED_ACTIONS,
      f"Missing: {SUPPORTED_ACTIONS - registered}"
      if registered != SUPPORTED_ACTIONS else "")

# 6. Static dispatch checks - verify handler signatures
print("\n--- Handler signature checks ---")
for action, fn in HANDLERS.items():
    import inspect
    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())
    check(f"'{action}' handler has correct signature (plan, ctx)",
          params == ["plan", "ctx"], f"Got params: {params}")

# Summary
print("\n" + "=" * 60)
print(f"RESULTS:  {PASS} passed, {FAIL} failed out of {PASS + FAIL}")
print("=" * 60)

# Also verify file_manager ops
print("\n--- file_manager ops ---")
from file_manager import list_ops, _OPS
ops = list_ops()
for op in sorted(ops):
    check(f"file_manager '{op}' handler exists", op in _OPS)

print("\n--- pc_control ops ---")
from pc_control import list_commands, _OPS as pc_ops
cmds = list_commands()
for cmd in sorted(cmds):
    check(f"pc_control '{cmd}' handler exists", cmd in pc_ops)

print("\n" + "=" * 60)
print(f"FINAL:  {PASS} passed, {FAIL} failed")
print("=" * 60)

if FAIL > 0:
    import sys; sys.exit(1)
