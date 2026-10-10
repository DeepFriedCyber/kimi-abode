#!/usr/bin/env python3
"""Patch router.py to load Sandbach properties from JSON file"""

import re
import json

JSON_PATH = "ai-service/data/sandbach_properties.json"
PY_FILE = "ai-service/app/router.py"

with open(JSON_PATH, 'r') as f:
    sandbach_data = json.load(f)

# Read the current router.py
with open(PY_FILE, 'r') as f:
    content = f.read()

# Create the properties array string
props_str = "        " + ",\n".join([json.dumps(p) for p in sandbach_data])

# Find and replace the mock_properties section
old_section = '''            {
                "id": 1,
                "address_line1": "123 High Street",
                "town": "Manchester","'''

new_section = f'''        # Sandbach historical listings data (~500 properties)
        self.mock_properties = [{props_str}]
    ]'''

# Actually we need to replace the whole section properly
old_mock_block = '''self.mock_properties = [
            {
                "id": 1,
                "address_line1": "123 High Street",
                "town": "Manchester",
                "postcode": "M1 1AA",
                "outcode": "M1",
                "property_type": "terraced",
                "num_beds": 2,
                "price_paid": 250000,
                "date_sold": "2024-03-15",
                "latitude": 53.4808,
                "longitude": -2.2426,
            },
            {
                "id": 2,
                "address_line1": "45 Church Lane",
                "town": "Leeds",
                "postcode": "LS1 2BB",
                "outcode": "LS1",
                "property_type": "detached",
                "num_beds": 4,
                "price_paid": 650000,
                "date_sold": "2023-11-20",
                "latitude": 53.8008,
                "longitude": -1.5491,
            },
            {
                "id": 3,
                "address_line1": "78 Oak Avenue",
                "town": "Bristol",
                "postcode": "BS1 3DD",
                "outcode": "BS1",
                "property_type": "semi-detached",
                "num_beds": 3,
                "price_paid": 450000,
                "date_sold": "2024-01-10",
                "latitude": 51.4545,
                "longitude": -2.5879,
            },
        ]'''

new_mock_block = f'''        # Sandbach historical listings data (~500 properties)
        self.mock_properties = [
{props_str}]'''

if old_mock_block in content:
    print(f"✅ Found mock_properties block to replace")
    new_content = content.replace(old_mock_block, new_mock_block)
    
    with open(PY_FILE, 'w') as f:
        f.write(new_content)
    
    print(f"✅ Updated router.py with {len(sandbach_data)} Sandbach properties")
else:
    print("⚠️ Could not find exact match for mock_properties block")
    # Try partial replacement anyway
    if 'self.mock_properties = [' in content and '123 High Street' in content:
        print("✅ Found partial match - doing more aggressive replacement")
        # Use regex to replace from self.mock_properties to the closing ]
        pattern = r'self\.mock_properties\s*=\s*\[.*?\]'
        new_props_str = f'''# Sandbach historical listings data (~500 properties)
[{props_str}]'''
        new_content = re.sub(pattern, new_props_str, content, flags=re.DOTALL)
        
        with open(PY_FILE, 'w') as f:
            f.write(new_content)
        
        print(f"✅ Updated router.py with {len(sandbach_data)} Sandbach properties")
    else:
        print("❌ Could not locate mock_properties in file")

print("\n📝 Checking the update...")
with open(PY_FILE, 'r') as f:
    check_content = f.read()
    
if 'Sandbach historical listings' in check_content and len(check_content.split('# Sandbach')[1].split(']')[0].count('address_line1')) >= 500:
    print("✅ Sandbach data successfully loaded into router.py")
else:
    print(f"⚠️ May need manual verification (found {check_content.count('address_line1')} occurrences)")
