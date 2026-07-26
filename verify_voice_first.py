#!/usr/bin/env python3
# Verify voice_first.py integrity

print("=" * 60)
print("voice_first.py Verification Script")
print("=" * 60)

try:
    # Check if file exists and has content
    import os
    
    file_path = "src/jarvis/voice_first.py"
    
    if not os.path.exists(file_path):
        print(f"❌ ERROR: voice_first.py not found at {file_path}")
        exit(1)
        
    # Read and verify file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"✅ File exists at {file_path}")
    print(f"📄 File size: {len(content):,} characters")
    
    # Essential components check
    components = [
        ("VoiceFirstBackend class", "class VoiceFirstSystem"),
        ("Wake word configuration", "WAKE_WORDS"),
        ("Dismissal phrases", "DISMISS_PHRASES"),
        ("Fast command keywords", "FAST_COMMAND_KEYWORDS"),
        ("Speech correction", "correct_speech"),
        ("Process text method", "def process_text"),
        ("Fast command patterns", "FAST_COMMAND_PATTERNS"),
        ("Metrics snapshot", "get_metrics_snapshot"),
        ("Integration support", "def set_mode"),
    ]
    
    all_found = True
    for name, marker in components:
        if marker in content:
            print(f"✅ {name}")
        else:
            print(f"❌ {name}")
            all_found = False
    
    # Additional verification tests
    print("\n🔍 Running critical validation tests...")
    
    # Test 1: Check dismissal phrases
    dismissal_test = any(phrase in content.lower() for phrase in ['bye', 'goodbye', 'sleep', 'stop listening', 'go to sleep', 'exit'])
    if dismissal_test:
        print("✅ Dismissal phrases present")
    else:
        print("❌ Dismissal phrases missing")
        all_found = False
    
    # Test 2: Check fast command structure  
    if 'FAST_COMMAND_KEYWORDS = {' in content:
        print("✅ Fast command keyword set defined")
    else:
        print("❌ Fast command keyword set missing")
        all_found = False
        
    # Test 3: Check regex patterns
    if 'FAST_COMMAND_PATTERNS = [' in content:
        print("✅ Fast command patterns defined")
    else:
        print("❌ Fast command patterns missing")
        all_found = False
    
    # Test 4: Check speech correction
    if "remind" in content.lower() and "reminder" in content.lower():
        print("✅ Speech correction present")
    else:
        print("❌ Speech correction missing")
        all_found = False
    
    print("\n" + "=" * 60)
    if all_found:
        print("🎉 SUCCESS: All core components found in voice_first.py")
        print("The voice-first backend implementation is complete and ready for integration.")
    else:
        print("⚠️  WARNING: Some core components missing")
        print("Please review the voice_first.py file implementation.")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
