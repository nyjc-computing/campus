#!/usr/bin/env python3
"""Script to update imports to use the new campus namespace structure."""

import os
import re
from pathlib import Path

def update_imports_in_file(file_path):
    """Update imports in a single Python file."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Update imports to use campus namespace
        # Pattern: from apps. -> from campus.apps.
        content = re.sub(r'^from apps\.', 'from campus.apps.', content, flags=re.MULTILINE)
        
        # Pattern: from common. -> from campus.common.
        content = re.sub(r'^from common\.', 'from campus.common.', content, flags=re.MULTILINE)
        
        # Pattern: from services. -> from campus.services.
        content = re.sub(r'^from services\.', 'from campus.services.', content, flags=re.MULTILINE)
        
        # Pattern: from storage. -> from campus.storage.
        content = re.sub(r'^from storage\.', 'from campus.storage.', content, flags=re.MULTILINE)
        
        # Pattern: from apps -> from campus.apps (without dot)
        content = re.sub(r'^from apps$', 'from campus.apps', content, flags=re.MULTILINE)
        content = re.sub(r'^from apps ', 'from campus.apps ', content, flags=re.MULTILINE)
        
        # Pattern: from common -> from campus.common (without dot)
        content = re.sub(r'^from common$', 'from campus.common', content, flags=re.MULTILINE)
        content = re.sub(r'^from common ', 'from campus.common ', content, flags=re.MULTILINE)
        
        # Pattern: from services -> from campus.services (without dot)
        content = re.sub(r'^from services$', 'from campus.services', content, flags=re.MULTILINE)
        content = re.sub(r'^from services ', 'from campus.services ', content, flags=re.MULTILINE)
        
        # Pattern: from storage -> from campus.storage (without dot)
        content = re.sub(r'^from storage$', 'from campus.storage', content, flags=re.MULTILINE)
        content = re.sub(r'^from storage ', 'from campus.storage ', content, flags=re.MULTILINE)
        
        # Pattern: import apps -> import campus.apps
        content = re.sub(r'^import apps$', 'import campus.apps', content, flags=re.MULTILINE)
        content = re.sub(r'^import common$', 'import campus.common', content, flags=re.MULTILINE)
        content = re.sub(r'^import services$', 'import campus.services', content, flags=re.MULTILINE)
        content = re.sub(r'^import storage$', 'import campus.storage', content, flags=re.MULTILINE)
        
        # Pattern: import common. -> import campus.common.
        content = re.sub(r'^import common\.', 'import campus.common.', content, flags=re.MULTILINE)
        content = re.sub(r'^import apps\.', 'import campus.apps.', content, flags=re.MULTILINE)
        content = re.sub(r'^import services\.', 'import campus.services.', content, flags=re.MULTILINE)
        content = re.sub(r'^import storage\.', 'import campus.storage.', content, flags=re.MULTILINE)
        
        if content != original_content:
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"Updated: {file_path}")
            return True
        
        return False
        
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def main():
    """Update all Python files in the campus directory."""
    campus_dir = Path("/workspaces/campus/campus")
    updated_files = []
    
    for py_file in campus_dir.rglob("*.py"):
        if update_imports_in_file(py_file):
            updated_files.append(py_file)
    
    print(f"\nUpdated {len(updated_files)} files:")
    for file_path in updated_files:
        print(f"  {file_path}")

if __name__ == "__main__":
    main()
