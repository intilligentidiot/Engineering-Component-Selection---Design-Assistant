import hashlib
from app.database.database import SessionLocal
from app.database.models import DiscoverySearchCache
from app.engine.discover import build_query_fingerprint

def clear_specific_cache():
    print("Connecting to database...")
    db = SessionLocal()
    
    try:
        # Generate the exact fingerprint for the test inputs
        fp = build_query_fingerprint(
            required_torque_nm=1.0, 
            required_speed_rpm=35.0, 
            max_voltage_v=20.0, 
            service_factor=1.0
        )
        
        print(f"Target Fingerprint: {fp}")
        
        # Look for the exact cache entry
        existing = db.query(DiscoverySearchCache).filter(
            DiscoverySearchCache.query_fingerprint == fp
        ).first()
        
        if existing:
            print(f"✅ Found existing cache entry created by provider: '{existing.provider}'")
            db.delete(existing)
            db.commit()
            print("✅ Cache entry successfully removed. Next search will be a true Cache MISS.")
        else:
            print("ℹ️ Cache entry not found. Next search is already guaranteed to be a Cache MISS.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clear_specific_cache()
