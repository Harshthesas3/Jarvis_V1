"""Simple integration test for the skill system."""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that we can import the modules."""
    try:
        from jarvis.skills.registry import SkillRegistry
        from jarvis.skills.application import ApplicationRegistry
        from jarvis.skills.interfaces.skill import SkillInterface
        print("[OK] All imports successful")
        return True
    except Exception as e:
        print("[ERROR] Import failed: {}".format(e))
        return False

def test_skill_registry():
    """Test the SkillRegistry."""
    try:
        from jarvis.skills.registry import SkillRegistry, SkillExecutionResult
        from jarvis.skills.interfaces.skill import SkillInterface

        class DummySkill(SkillInterface):
            @property
            def name(self):
                return "dummy"

            @property
            def description(self):
                return "A dummy skill"

            def execute(self, **kwargs):
                return {"success": True, "reason": "Dummy executed", "logs": [], "data": None}

        registry = SkillRegistry()
        skill = DummySkill()
        assert registry.register_skill("dummy", skill) == True
        retrieved = registry.get_skill("dummy")
        assert retrieved is not None
        result = registry.execute_skill("dummy")
        # SkillExecutionResult is not a dict, check its attributes
        assert result.success == True
        assert "Dummy executed" in result.reason
        print("[OK] SkillRegistry tests passed")
        return True
    except Exception as e:
        print("[ERROR] SkillRegistry test failed: {}".format(e))
        import traceback
        traceback.print_exc()
        return False

def test_application_registry():
    """Test the ApplicationRegistry."""
    try:
        from jarvis.skills.application import ApplicationRegistry

        registry = ApplicationRegistry()
        # The register_application method takes name and executable
        # It internally creates ApplicationInfo with path=executable
        assert registry.register_application("testapp", "test.exe", description="Test app") == True
        app = registry.get_application("testapp")
        assert app is not None
        assert app.name == "testapp"
        assert app.executable == "test.exe"
        assert app.path == "test.exe"  # path should equal executable
        print("[OK] ApplicationRegistry tests passed")
        return True
    except Exception as e:
        print("[ERROR] ApplicationRegistry test failed: {}".format(e))
        import traceback
        traceback.print_exc()
        return False

def run_tests():
    """Run all tests."""
    print("[INFO] Running simple integration tests...\n")
    results = [
        test_imports(),
        test_skill_registry(),
        test_application_registry()
    ]
    if all(results):
        print("\n[SUCCESS] All tests passed!")
        return True
    else:
        print("\n[FAILURE] Some tests failed.")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)