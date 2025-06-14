#!/usr/bin/env python3
"""
Test script to verify automatic DSPy type registration works.
"""

def test_automatic_type_registration():
    """Test that importing from attachments.dspy automatically registers the type."""
    print("🧪 Testing automatic DSPy type registration...")
    
    # Import should automatically register the type
    from attachments.dspy import Attachments
    import typing
    
    # Verify registration worked
    assert hasattr(typing, 'Attachments'), "Attachments should be automatically registered in typing module"
    assert typing.Attachments is Attachments, "typing.Attachments should point to our Attachments class"
    
    print("✅ Automatic type registration successful!")
    return True

def test_string_signature_parsing():
    """Test that string-based DSPy signatures can parse Attachments type."""
    print("🧪 Testing DSPy string signature parsing...")
    
    from attachments.dspy import Attachments
    import dspy
    
    try:
        # This should work now without manual type registration
        signature = dspy.Signature("document: Attachments -> summary: str")
        print("✅ String signature parsing successful!")
        return True
    except ValueError as e:
        if "Unknown name: Attachments" in str(e):
            print(f"❌ String signature parsing failed: {e}")
            return False
        else:
            # Some other error, re-raise
            raise

def test_class_signature():
    """Test that class-based DSPy signatures work."""
    print("🧪 Testing DSPy class signature...")
    
    from attachments.dspy import Attachments
    import dspy
    
    try:
        class TestSignature(dspy.Signature):
            """Test signature with Attachments type."""
            document: Attachments = dspy.InputField()
            summary: str = dspy.OutputField()
        
        print("✅ Class signature creation successful!")
        return True
    except Exception as e:
        print(f"❌ Class signature creation failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Running DSPy automatic type registration tests...\n")
    
    tests = [
        test_automatic_type_registration,
        test_string_signature_parsing,
        test_class_signature,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    passed = sum(results)
    total = len(results)
    
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Automatic DSPy type registration is working perfectly!")
        exit(0)
    else:
        print("💥 Some tests failed. Check the output above for details.")
        exit(1) 