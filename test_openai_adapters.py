#!/usr/bin/env python3
"""Test both OpenAI adapters with real API calls."""

import os

def test_chat_adapter():
    """Test the chat completions adapter."""
    print("🤖 Testing OpenAI Chat Completions Adapter...")
    
    try:
        from attachments import Attachments
        from attachments.core import adapt, load
        
        # Find a test file
        test_file = None
        for file in ["examples/sample.pdf", "examples/sample.pptx", "sample.png"]:
            if os.path.exists(file):
                test_file = file
                break
        
        if not test_file:
            print("   ⚠️  No test files available")
            return True
        
        # Test low-level adapter
        att = load.pdf(test_file) if test_file.endswith('.pdf') else load.pptx(test_file)
        chat_messages = adapt.openai_chat(att, "Summarize this document briefly")
        
        print(f"   ✅ Low-level adapter: {len(chat_messages)} messages")
        print(f"       Message format: {list(chat_messages[0].keys())}")
        
        # Test high-level interface (should use chat adapter by default)
        ctx = Attachments(test_file)
        openai_messages = ctx.to_openai("Summarize this document briefly")
        
        print(f"   ✅ High-level interface: {len(openai_messages)} messages")
        
        # Make actual API call
        try:
            from openai import OpenAI
            client = OpenAI()
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=chat_messages,
                max_tokens=50
            )
            
            result = response.choices[0].message.content
            print(f"   ✅ API call successful: {len(result)} chars")
            print(f"       Response: {result[:80]}...")
            
        except Exception as e:
            print(f"   ⚠️  API call failed: {e}")
    
    except Exception as e:
        print(f"   ❌ Chat adapter test failed: {e}")
        return False
    
    return True


def test_structured_adapter():
    """Test the structured outputs adapter."""
    print("\n🤖 Testing OpenAI Structured Outputs Adapter...")
    
    try:
        from attachments.core import adapt, load
        
        # Find a test file
        test_file = None
        for file in ["examples/sample.pdf", "examples/sample.pptx", "sample.png"]:
            if os.path.exists(file):
                test_file = file
                break
        
        if not test_file:
            print("   ⚠️  No test files available")
            return True
        
        # Define a JSON schema for structured output
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "document_summary",
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Document title or main topic"},
                        "summary": {"type": "string", "description": "Brief 1-2 sentence summary"},
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3-5 key points from the document"
                        }
                    },
                    "required": ["title", "summary", "key_points"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        
        # Test the structured adapter
        att = load.pdf(test_file) if test_file.endswith('.pdf') else load.pptx(test_file)
        structured_payload = adapt.openai_structured(
            att, 
            "Analyze this document and provide a structured summary",
            response_format
        )
        
        print(f"   ✅ Structured adapter: {len(structured_payload)} payload keys")
        print(f"       Payload keys: {list(structured_payload.keys())}")
        print(f"       Messages: {len(structured_payload['messages'])}")
        print(f"       Has response_format: {'response_format' in structured_payload}")
        
        # Make actual API call with structured output
        try:
            from openai import OpenAI
            client = OpenAI()
            
            response = client.chat.completions.create(**structured_payload, max_tokens=200)
            
            result = response.choices[0].message.content
            print(f"   ✅ Structured API call successful: {len(result)} chars")
            print(f"       Structured response: {result[:100]}...")
            
            # Try to parse as JSON to verify structure
            import json
            parsed = json.loads(result)
            required_fields = ["title", "summary", "key_points"]
            has_all_fields = all(field in parsed for field in required_fields)
            print(f"   ✅ JSON structure valid: {has_all_fields}")
            if has_all_fields:
                print(f"       Title: {parsed['title']}")
                print(f"       Key points: {len(parsed['key_points'])} items")
            
        except Exception as e:
            print(f"   ⚠️  Structured API call failed: {e}")
    
    except Exception as e:
        print(f"   ❌ Structured adapter test failed: {e}")
        return False
    
    return True


def test_adapter_compatibility():
    """Test that adapters work with multiple attachments."""
    print("\n🔗 Testing Multi-Attachment Compatibility...")
    
    try:
        from attachments import Attachments
        from attachments.core import adapt, load
        
        # Find test files
        test_files = []
        for file in ["examples/sample.pdf", "examples/sample.pptx", "sample.png"]:
            if os.path.exists(file):
                test_files.append(file)
        
        if len(test_files) < 2:
            print("   ⚠️  Need at least 2 test files for multi-attachment test")
            return True
        
        # Test high-level interface with multiple files
        ctx = Attachments(*test_files[:2])  # Use first 2 files
        
        # The high-level interface should combine all content
        openai_messages = ctx.to_openai("Compare these documents")
        
        print(f"   ✅ Multi-attachment: {len(openai_messages)} messages")
        print(f"       Content items: {len(openai_messages[0]['content'])}")
        
        # Test individual attachment adapters
        for i, test_file in enumerate(test_files[:2]):
            att = load.pdf(test_file) if test_file.endswith('.pdf') else load.pptx(test_file)
            individual_messages = adapt.openai_chat(att, f"Analyze document {i+1}")
            print(f"   ✅ Individual {i+1}: {len(individual_messages)} messages")
        
    except Exception as e:
        print(f"   ❌ Compatibility test failed: {e}")
        return False
    
    return True


def main():
    """Run all OpenAI adapter tests."""
    print("🧪 Testing OpenAI Adapters")
    print("=" * 40)
    
    tests = [
        test_chat_adapter,
        test_structured_adapter,
        test_adapter_compatibility
    ]
    
    results = []
    for test in tests:
        try:
            success = test()
            results.append(success)
        except Exception as e:
            print(f"   💥 Test crashed: {e}")
            results.append(False)
    
    print(f"\n📊 Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("🎉 All OpenAI adapters working correctly!")
        return 0
    else:
        print("❌ Some OpenAI adapter tests failed")
        return 1


if __name__ == "__main__":
    exit(main()) 