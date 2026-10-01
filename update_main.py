import re

with open('static/js/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

part_to_find = """<tr><td>Discovered At</td><td>${rec.verification.discovered_at}</td></tr>"""

new_part = """<tr><td>Discovered At</td><td>${rec.verification.discovered_at}</td></tr>
                        ${rec.specification_source ? `<tr><td>Spec Source</td><td>${rec.specification_source}</td></tr>` : ''}
                        ${rec.specification_source_url ? `<tr><td>Spec URL</td><td><a href="${rec.specification_source_url}" target="_blank" style="color:var(--accent-blue)">View Source</a></td></tr>` : ''}
                        ${rec.extracted_at ? `<tr><td>Extracted At</td><td>${new Date(rec.extracted_at).toLocaleString()}</td></tr>` : ''}"""

if part_to_find in content:
    content = content.replace(part_to_find, new_part)
    with open('static/js/main.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated main.js successfully")
else:
    print("Could not find the target string")
