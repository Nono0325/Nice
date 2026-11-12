import time
from backend.config import config_mgr
from backend.motion_engine import MotionEngine

def test_all():
    print("[TEST 1] 初始化 MotionEngine...")
    engine = MotionEngine(config_mgr)
    assert engine.is_simulation == True, "Should be in simulation mode"
    print("✓ MotionEngine 初始化完成 (模擬模式)")

    print("\n[TEST 2] 測試馬達致能鎖定 (Motor Lock)...")
    engine.set_motor_lock("ALL", True)
    assert engine.motor_x.is_locked == True
    assert engine.motor_z.is_locked == True
    print("✓ 馬達全軸鎖定成功")

    engine.set_motor_lock("X", False)
    assert engine.motor_x.is_locked == False
    assert engine.motor_z.is_locked == True
    print("✓ X軸單軸解鎖成功")

    engine.set_motor_lock("X", True)
    assert engine.motor_x.is_locked == True

    print("\n[TEST 3] 測試電磁鐵控制 (LSD-P25/20)...")
    engine.electromagnets.set_channel(1, True)
    engine.electromagnets.set_channel(3, True)
    states = engine.electromagnets.get_states()
    assert states["em1"] == True
    assert states["em2"] == False
    assert states["em3"] == True
    assert states["em4"] == False
    print("✓ 電磁鐵單獨開關測試成功")

    engine.electromagnets.set_all(False)
    states = engine.electromagnets.get_states()
    assert states["any_active"] == False
    print("✓ 電磁鐵全部關閉成功")

    print("\n[TEST 4] 測試寸動位移 (Jog)...")
    initial_x = engine.motor_x.position_mm
    engine.jog("X", 1, 20.0, speed_mm_s=100.0)
    time.sleep(0.3)
    print(f"X軸運動中座標: {engine.motor_x.position_mm:.2f}mm")
    time.sleep(0.2)
    assert engine.motor_x.position_mm > initial_x
    print(f"✓ X軸寸動完成，最終位置: {engine.motor_x.position_mm:.2f}mm")

    print("\n[TEST 5] 測試自動歸零序列 (Auto Homing)...")
    engine.start_homing("ALL")
    # 等待歸零完成 (最多等 8 秒)
    for _ in range(80):
        time.sleep(0.1)
        if engine.state == "IDLE":
            break
    print(f"歸零完成後狀態: state={engine.state}, X={engine.motor_x.position_mm:.2f}mm, Z={engine.motor_z.position_mm:.2f}mm")
    assert engine.motor_x.is_homed == True
    assert engine.motor_z.is_homed == True
    print("✓ 自動歸零序列測試通過！")

    print("\n[TEST 6] 測試 13 顆接近開關讀取...")
    sensors = engine.sensor_monitor.read_all()
    assert "x_left" in sensors
    assert "z_up" in sensors
    assert "arm_1" in sensors
    assert "arm_8" in sensors
    print(f"✓ 感測器狀態讀取正常: {len(sensors)} 項訊號")

    print("\n===============================")
    print("所有核心單元測試全部通過！100% OK")
    print("===============================")

if __name__ == "__main__":
    test_all()
