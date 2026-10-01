import re

with open('app/engine/discover.py', 'r', encoding='utf-8') as f:
    content = f.read()

part_to_find = """            "cache_hit":    cache_hit,
            "cache_source": cache_source,"""

new_part = """            "cache_hit":    cache_hit,
            "cache_source": cache_source,
            # Stage 6.3 provenance fields
            "specification_source": raw.get("specification_source"),
            "specification_source_url": raw.get("specification_source_url"),
            "extracted_at": raw.get("extracted_at"),"""

if part_to_find in content:
    content = content.replace(part_to_find, new_part)
    with open('app/engine/discover.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated discover.py successfully")
else:
    print("Could not find the target string")
