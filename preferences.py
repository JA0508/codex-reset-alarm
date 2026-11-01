"""Shared local notification preference."""
import json
import os
import tempfile
from pathlib import Path
PATH = Path.home() / 'Library/Application Support/CodexResetAlarm/preferences.json'

def enabled():
    try:
        value = json.loads(PATH.read_text()).get('enabled', True)
        return value if type(value) is bool else True
    except (OSError, ValueError, AttributeError):
        return True

def save(value):
    if type(value) is not bool:
        raise ValueError('enabled must be boolean')
    PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.preferences-', dir=PATH.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w') as output:
            json.dump({'enabled': value}, output)
        os.replace(temporary, PATH)
    finally:
        temporary.unlink(missing_ok=True)

def parse(body):
    value = json.loads(body)
    if not isinstance(value, dict) or set(value) != {'enabled'} or type(value['enabled']) is not bool:
        raise ValueError('Expected enabled boolean')
    return value['enabled']
