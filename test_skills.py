"""Integration tests for the skill system."""

import os
import sys

# Add the src directory to the path so we can import jarvis modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_skill_registry():
    """Test the SkillRegistry functionality."""
    print("Testing SkillRegistry...")

    from jarvis.skills.registry import SkillRegistry
    from jarvis.skills.interfaces.skill import SkillInterface

    class TestSkill(SkillInterface):
        @property
        def name(self) -> str:
            return "test_skill"

        @property
        def description(self) -> str:
            return "A test skill"

        def execute(self, **kwargs) -> dict:
            return {
                "success": True,
                "reason": "Test executed successfully",
                "logs": ["Test log"],
                "data": kwargs.get("data", "default")
            }

    registry = SkillRegistry()

    # Test registration
    skill = TestSkill()
    assert registry.register_skill("test_skill", skill) == True
    assert registry.register_skill("test_skill", skill) == False  # Duplicate

    # Test retrieval
    retrieved = registry.get_skill("test_skill")
    assert retrieved is not None
    assert retrieved.name == "test_skill"

    # Test execution
    result = registry.execute_skill("test_skill", data="test_data")
    assert result.success == True
    assert result.data == "test_data"
    assert "Test executed successfully" in result.reason

    # Test listing
    skills = registry.list_skills()
    assert "test_skill" in skills

    # Test unregistration
    assert registry.unregister_skill("test_skill") == True
    assert registry.unregister_skill("test_skill") == False  # Already removed
    assert registry.get_skill("test_skill") is None

    print("✓ SkillRegistry tests passed")

def test_application_registry():
    """Test the ApplicationRegistry functionality."""
    print("Testing ApplicationRegistry...")

    from jarvis.skills.application import ApplicationRegistry

    registry = ApplicationRegistry()

    # Test registration
    assert registry.register_application("notepad", "notepad.exe", description="Notepad text editor") == True
    assert registry.register_application("notepad", "notepad.exe") == False  # Duplicate

    # Test retrieval
    app = registry.get_application("notepad")
    assert app is not None
    assert app.name == "notepad"
    assert app.executable == "notepad.exe"
    assert app.description == "Notepad text editor"

    # Test listing
    apps = registry.list_applications()
    assert "notepad" in apps

    # Test execution (simulated)
    result = registry.execute_application("notepad")
    # This will fail since notepad.exe might not be in PATH in test env, but we can check structure
    assert "success" in result
    assert "reason" in result
    assert "logs" in result
    assert "execution_time" in result

    # Test unregistration
    assert registry.unregister_application("notepad") == True
    assert registry.unregister_application("notepad") == False  # Already removed
    assert registry.get_application("notepad") is None

    print("✓ ApplicationRegistry tests passed")

def test_windows_skill():
    """Test the WindowsSkill functionality."""
    print("Testing WindowsSkill...")

    from jarvis.skills.windows import WindowsSkill

    skill = WindowsSkill()
    assert skill.name == "windows"
    assert "Windows system operations" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test list apps action (should not crash)
    result = skill.execute(action="find_installed_apps")
    # Should return a structured response even if no apps found in test env
    assert "success" in result
    print("✓ WindowsSkill tests passed")

def test_browser_skill():
    """Test the BrowserSkill functionality."""
    print("Testing BrowserSkill...")

    from jarvis.skills.browser import BrowserSkill

    skill = BrowserSkill()
    assert skill.name == "browser"
    assert "Browser automation" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    print("✓ BrowserSkill tests passed")

def test_explorer_skill():
    """Test the ExplorerSkill functionality."""
    print("Testing ExplorerSkill...")

    from jarvis.skills.explorer import ExplorerSkill

    skill = ExplorerSkill()
    assert skill.name == "explorer"
    assert "File system exploration" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test list_directory on current directory
    result = skill.execute(action="list_directory", path=".")
    assert result["success"] == True
    assert "items" in result["data"]
    assert "count" in result["data"]

    # Test file_exists on this file
    result = skill.execute(action="file_exists", path=__file__)
    assert result["success"] == True
    assert result["data"]["exists"] == True

    # Test resolve_path
    result = skill.execute(action="resolve_path", path=".")
    assert result["success"] == True
    assert "resolved" in result["data"]

    print("✓ ExplorerSkill tests passed")

def test_vscode_skill():
    """Test the VSCodeSkill functionality."""
    print("Testing VSCodeSkill...")

    from jarvis.skills.vscode import VSCodeSkill

    skill = VSCodeSkill()
    assert skill.name == "vscode"
    assert "VS Code editor operations" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    print("✓ VSCodeSkill tests passed")

def test_terminal_skill():
    """Test the TerminalSkill functionality."""
    print("Testing TerminalSkill...")

    from jarvis.skills.terminal import TerminalSkill

    skill = TerminalSkill()
    assert skill.name == "terminal"
    assert "Terminal operations" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test get_current_directory
    result = skill.execute(action="get_current_directory")
    assert result["success"] == True
    assert "current_directory" in result["data"]

    # Test execute_command with a simple command
    result = skill.execute(action="execute_command", command="echo hello")
    assert result["success"] == True
    assert "hello" in result["data"]["stdout"]

    print("✓ TerminalSkill tests passed")

def test_clipboard_skill():
    """Test the ClipboardSkill functionality."""
    print("Testing ClipboardSkill...")

    from jarvis.skills.clipboard import ClipboardSkill

    skill = ClipboardSkill()
    assert skill.name == "clipboard"
    assert "Clipboard operations" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test format_available
    result = skill.execute(action="format_available", format="text")
    assert "success" in result
    assert "available" in result["data"]

    print("✓ ClipboardSkill tests passed")

def test_power_skill():
    """Test the PowerSkill functionality."""
    print("Testing PowerSkill...")

    from jarvis.skills.power import PowerSkill

    skill = PowerSkill()
    assert skill.name == "power"
    assert "Power management operations" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test get_battery_status (should return structured response)
    result = skill.execute(action="get_battery_status")
    assert "success" in result
    assert "reason" in result
    assert "logs" in result
    assert "data" in result

    print("✓ PowerSkill tests passed")

def test_notification_skill():
    """Test the NotificationSkill functionality."""
    print("Testing NotificationSkill...")

    from jarvis.skills.notification import NotificationSkill

    skill = NotificationSkill()
    assert skill.name == "notification"
    assert "System notifications" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test show_alert
    result = skill.execute(action="show_alert", title="Test", message="This is a test")
    assert result["success"] == True
    assert "Alert shown" in result["reason"]

    print("✓ NotificationSkill tests passed")

def test_calendar_skill():
    """Test the CalendarSkill functionality."""
    print("Testing CalendarSkill...")

    from jarvis.skills.calendar import CalendarSkill

    skill = CalendarSkill()
    assert skill.name == "calendar"
    assert "Calendar operations" in skill.description

    # Test unknown action
    result = skill.execute(action="unknown_action")
    assert result["success"] == False
    assert "Unknown action" in result["reason"]

    # Test create_event
    result = skill.execute(
        action="create_event",
        title="Test Event",
        start_time="2023-12-25T10:00:00",
        end_time="2023-12-25T11:00:00",
        description="A test event",
        location="Test Location"
    )
    assert result["success"] == True
    assert "Event created" in result["reason"]
    assert "data" in result
    assert "id" in result["data"]

    # Test get_today_events
    result = skill.execute(action="get_today_events")
    assert "success" in result
    assert "events" in result["data"]

    print("✓ CalendarSkill tests passed")

def run_all_tests():
    """Run all tests."""
    print("Running integration tests for JARVIS skill system...\n")

    try:
        test_skill_registry()
        test_application_registry()
        test_windows_skill()
        test_browser_skill()
        test_explorer_skill()
        test_vscode_skill()
        test_terminal_skill()
        test_clipboard_skill()
        test_power_skill()
        test_notification_skill()
        test_calendar_skill()

        print("\n🎉 All tests passed!")
        return True
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)