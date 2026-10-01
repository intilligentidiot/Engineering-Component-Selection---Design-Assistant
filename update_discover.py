import sys

with open('app/engine/discover.py', 'r', encoding='utf-8') as f:
    content = f.read()

part_to_remove = """        # Write results back to cache
        write_cache(
            db, required_torque_nm, required_speed_rpm,
            max_voltage_v, service_factor, raw_results, provider_name
        )"""

new_part = """        # Stage 6.2: Relevance filter BEFORE enrichment and cache
        relevant_raw = []
        for raw in raw_results:
            if not is_relevant_product_result(raw):
                title_preview = (raw.get("product_name") or raw.get("title") or "")[:80]
                print(f"[Relevance REJECT] '{title_preview}' - not a motor/gearbox product")
                continue
            relevant_raw.append(raw)
            
        # Stage 6.3: External Product Specification Enrichment
        from app.engine.product_enrichment import ProductEnricher
        enricher = ProductEnricher()
        enriched_results = enricher.enrich(relevant_raw)

        # Write results back to cache
        write_cache(
            db, required_torque_nm, required_speed_rpm,
            max_voltage_v, service_factor, enriched_results, provider_name
        )
        
        raw_results = enriched_results"""

if part_to_remove in content:
    content = content.replace(part_to_remove, new_part)
    with open('app/engine/discover.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated discover.py successfully")
else:
    print("Could not find the target string")
