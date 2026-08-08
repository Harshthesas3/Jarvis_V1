"""Test script to verify memory manager initialization."""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from jarvis.memory.manager import get_memory_manager
    print("[OK] Memory manager imported successfully")

    # Initialize memory manager
    mm = get_memory_manager()
    print("[OK] Memory manager initialized")

    # Test basic functionality
    print("[OK] Testing conversation memory...")
    mm.conversation.add_message("user", "Hello, test message")
    history = mm.conversation.get_history()
    print(f"[OK] Conversation history: {len(history)} messages")

    print("[OK] Testing user memory...")
    mm.user.set_preference("test_key", "test_value")
    value = mm.user.get_preference("test_key", "default")
    print(f"[OK] User preference: {value}")

    print("[OK] Testing project memory...")
    proj_id = mm.project.register_project("test_project", "/tmp/test")
    print(f"[OK] Project registered with ID: {proj_id}")

    print("[OK] Testing task memory...")
    task_id = mm.task.create_task("Test task", "This is a test task")
    print(f"[OK] Task created with ID: {task_id}")

    print("[OK] Testing skill memory...")
    skill_id = mm.skill.register_skill("test_skill", "A test skill")
    print(f"[OK] Skill registered with ID: {skill_id}")

    print("[OK] Testing execution memory...")
    log_id = mm.execution.log_execution("test_component", "test_action", "success", 0.1)
    print(f"[OK] Execution logged with ID: {log_id}")

    print("\n[OK] All memory systems initialized and tested successfully!")

except Exception as e:
    print(f"[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()