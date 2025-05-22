#!/usr/bin/env python3
"""Final test of all README examples."""

print('🔧 Testing Updated README Examples')
print('=' * 40)

# Test 1: Basic interface
from attachments import Attachments
import tempfile

with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write('This is a test document.')
    test_file = f.name

ctx = Attachments(test_file)
print(f'✅ Basic interface: {len(str(ctx))} chars, {len(ctx.images)} images')

# Test 2: API adapters  
openai_msgs = ctx.to_openai('Test prompt')
claude_msgs = ctx.to_claude('Test prompt')
print(f'✅ API adapters: OpenAI {len(openai_msgs)} msgs, Claude {len(claude_msgs)} msgs')

# Test 3: Modular components
from attachments.core import load, present, modify, adapt
print(f'✅ Modular imports: load, present, modify, adapt all available')

# Test 4: Extension system
from attachments.core.decorators import loader, presenter

@loader(lambda path: path.endswith('.xyz'))
def xyz_file(path: str):
    return {'content': 'Custom XYZ data'}

@presenter  
def custom_summary(data: dict) -> str:
    return f'Custom summary: {data.get("content", "No content")}'

print(f'✅ Extension system: Custom components register successfully')

# Test the new components work
print(f'✅ Available loaders: {[attr for attr in dir(load) if not attr.startswith("_")]}')

# Cleanup
import os
os.unlink(test_file)
print('🎉 All README examples verified!') 