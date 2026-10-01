import sys
from app.engine.product_enrichment import ProductEnricher

e = ProductEnricher()
candidates = [
    {
        "part_number": "JK36ZYT03A",  # Third model
        "product_url": "https://www.jkongmotor.com/planetary-geared-brush-dc-motor.html"
    }
]

print("Running ProductEnricher on jkongmotor URL for JK36ZYT03A...")
res = e.enrich(candidates)

print(f"\nExtracted length: {len(res)}")
if len(res) > 0:
    r = res[0]
    print("\nMotor specifications:")
    print(f"Voltage: {r.get('voltage_v')} V")
    print(f"Rated speed: {r.get('nominal_speed_rpm')} RPM")
    print(f"Rated torque: {r.get('nominal_torque_nm')} Nm")
    print(f"Output power: {r.get('power_w')} W")
    
    print("\nGearbox specifications:")
    print(f"Reduction ratio: {r.get('gear_ratio')} (If unambiguous)")
    print(f"Max torque: {r.get('max_output_torque_nm')} Nm")
    print(f"Efficiency: {r.get('efficiency')} % (as decimal)")
