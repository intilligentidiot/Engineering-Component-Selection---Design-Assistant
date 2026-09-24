from app.database.database import SessionLocal, engine, Base
from app.database.models import Manufacturer, Motor, Gearbox, DATA_STATUS_ENGINEERING_VERIFIED

def seed_database():
    # Recreate tables to ensure a clean state
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # 1. Add Manufacturers
    mfg_maxon = Manufacturer(name="Maxon", website="https://www.maxongroup.com")
    mfg_faulhaber = Manufacturer(name="Faulhaber", website="https://www.faulhaber.com")
    mfg_dunker = Manufacturer(name="Dunkermotoren", website="https://www.dunkermotoren.com")
    
    db.add_all([mfg_maxon, mfg_faulhaber, mfg_dunker])
    db.commit()

    # 2. Add Motors
    motors_data = [
        # Maxon EC-max series
        (mfg_maxon.id, "283837", 12.0, 16.0, 10000, 0.015, 0.03, "Maxon EC-max 16 datasheet"),
        (mfg_maxon.id, "283838", 24.0, 16.0, 9500, 0.015, 0.03, "Maxon EC-max 16 datasheet"),
        (mfg_maxon.id, "283840", 12.0, 22.0, 11000, 0.02, 0.045, "Maxon EC-max 22 datasheet"),
        (mfg_maxon.id, "283841", 24.0, 22.0, 10500, 0.02, 0.045, "Maxon EC-max 22 datasheet"),
        (mfg_maxon.id, "283843", 48.0, 40.0, 8000, 0.04, 0.08, "Maxon EC-max 30 datasheet"),
        (mfg_maxon.id, "283844", 24.0, 40.0, 8200, 0.04, 0.08, "Maxon EC-max 30 datasheet"),
        (mfg_maxon.id, "283855", 12.0, 120.0, 6000, 0.12, 0.25, "Maxon EC-max 40 datasheet"),
        (mfg_maxon.id, "283856", 24.0, 120.0, 6100, 0.12, 0.25, "Maxon EC-max 40 datasheet"),
        (mfg_maxon.id, "283857", 48.0, 120.0, 5900, 0.12, 0.25, "Maxon EC-max 40 datasheet"),
        (mfg_maxon.id, "283860", 24.0, 200.0, 5000, 0.25, 0.50, "Maxon EC-max 50 datasheet"),
        
        # Faulhaber Series
        (mfg_faulhaber.id, "1524E006SR", 6.0, 1.5, 12000, 0.002, 0.005, "Faulhaber DC-Motor datasheet"),
        (mfg_faulhaber.id, "1524E012SR", 12.0, 1.5, 12500, 0.002, 0.005, "Faulhaber DC-Motor datasheet"),
        (mfg_faulhaber.id, "2224U012SR", 12.0, 4.5, 9000, 0.01, 0.02, "Faulhaber DC-Motor datasheet"),
        (mfg_faulhaber.id, "2224U024SR", 24.0, 4.5, 8800, 0.01, 0.02, "Faulhaber DC-Motor datasheet"),
        (mfg_faulhaber.id, "3242G012CR", 12.0, 30.0, 7000, 0.05, 0.1, "Faulhaber DC-Motor datasheet"),
        (mfg_faulhaber.id, "3242G024CR", 24.0, 30.0, 7100, 0.05, 0.1, "Faulhaber DC-Motor datasheet"),
        
        # Dunkermotoren GR series
        (mfg_dunker.id, "GR42x25", 24.0, 20.0, 3000, 0.06, 0.15, "Dunkermotoren GR42 datasheet"),
        (mfg_dunker.id, "GR53x30", 24.0, 50.0, 3200, 0.14, 0.35, "Dunkermotoren GR53 datasheet"),
        (mfg_dunker.id, "GR63x25", 24.0, 70.0, 3300, 0.20, 0.50, "Dunkermotoren GR63 datasheet"),
        (mfg_dunker.id, "GR63x55", 24.0, 100.0, 3300, 0.30, 0.80, "Dunkermotoren GR63 datasheet"),
    ]

    motors = []
    for mfg_id, pn, v, p, rpm, t_nom, t_max, src in motors_data:
        motor = Motor(
            manufacturer_id=mfg_id,
            part_number=pn,
            voltage_v=v,
            continuous_power_w=p,
            nominal_speed_rpm=rpm,
            nominal_torque_nm=t_nom,
            max_torque_nm=t_max,
            source=src,
            source_url="https://engineering-docs.local",
            verification_status="Verified",
            verification_date="2026-09-24",
            data_status=DATA_STATUS_ENGINEERING_VERIFIED
        )
        motors.append(motor)
    
    db.add_all(motors)
    db.commit()

    # 3. Add Gearboxes
    gearboxes_data = [
        # Maxon GPX series
        (mfg_maxon.id, "GPX16_4", 4.4, 0.85, 12000, 0.4, "Maxon GPX 16 datasheet"),
        (mfg_maxon.id, "GPX16_16", 16.0, 0.75, 12000, 0.6, "Maxon GPX 16 datasheet"),
        (mfg_maxon.id, "GPX22_5", 5.4, 0.85, 10000, 1.2, "Maxon GPX 22 datasheet"),
        (mfg_maxon.id, "GPX22_21", 21.0, 0.75, 10000, 1.5, "Maxon GPX 22 datasheet"),
        (mfg_maxon.id, "GPX32_6", 6.0, 0.85, 8000, 4.0, "Maxon GPX 32 datasheet"),
        (mfg_maxon.id, "GPX32_24", 24.0, 0.75, 8000, 6.0, "Maxon GPX 32 datasheet"),
        (mfg_maxon.id, "GPX32_103", 103.0, 0.65, 8000, 8.0, "Maxon GPX 32 datasheet"),
        
        # Faulhaber Gearheads
        (mfg_faulhaber.id, "15/5_3.7", 3.7, 0.90, 12000, 0.1, "Faulhaber 15/5 datasheet"),
        (mfg_faulhaber.id, "15/5_14", 14.0, 0.81, 12000, 0.15, "Faulhaber 15/5 datasheet"),
        (mfg_faulhaber.id, "22/7_3.8", 3.8, 0.90, 10000, 0.6, "Faulhaber 22/7 datasheet"),
        (mfg_faulhaber.id, "22/7_14", 14.0, 0.81, 10000, 0.8, "Faulhaber 22/7 datasheet"),
        (mfg_faulhaber.id, "32/3_4", 4.0, 0.90, 8000, 4.5, "Faulhaber 32/3 datasheet"),
        (mfg_faulhaber.id, "32/3_14", 14.0, 0.80, 8000, 4.5, "Faulhaber 32/3 datasheet"),
        (mfg_faulhaber.id, "32/3_66", 66.0, 0.70, 8000, 4.5, "Faulhaber 32/3 datasheet"),

        # Dunkermotoren PLG series
        (mfg_dunker.id, "PLG42S_4", 4.0, 0.90, 5000, 1.4, "Dunkermotoren PLG42S datasheet"),
        (mfg_dunker.id, "PLG42S_16", 16.0, 0.80, 5000, 2.5, "Dunkermotoren PLG42S datasheet"),
        (mfg_dunker.id, "PLG52_4", 4.5, 0.90, 5000, 3.5, "Dunkermotoren PLG52 datasheet"),
        (mfg_dunker.id, "PLG52_16", 16.0, 0.80, 5000, 5.0, "Dunkermotoren PLG52 datasheet"),
        (mfg_dunker.id, "PLG52_64", 64.0, 0.70, 5000, 8.0, "Dunkermotoren PLG52 datasheet"),
        (mfg_dunker.id, "PLG63_10", 10.0, 0.80, 5000, 15.0, "Dunkermotoren PLG63 datasheet"),
    ]

    gearboxes = []
    for mfg_id, pn, ratio, eff, max_rpm, max_t, src in gearboxes_data:
        gb = Gearbox(
            manufacturer_id=mfg_id,
            part_number=pn,
            gear_ratio=ratio,
            efficiency=eff,
            max_input_speed_rpm=max_rpm,
            max_output_torque_nm=max_t,
            source=src,
            source_url="https://engineering-docs.local",
            verification_status="Verified",
            verification_date="2026-09-24",
            data_status=DATA_STATUS_ENGINEERING_VERIFIED
        )
        gearboxes.append(gb)
        
    db.add_all(gearboxes)
    db.commit()

    print(f"Successfully seeded database with {len(motors)} motors and {len(gearboxes)} gearboxes.")
    db.close()

if __name__ == "__main__":
    seed_database()
