import time
from fastapi.testclient import TestClient
from backend.server import app

def test_api():
    client = TestClient(app)
    
    # 1. 測試狀態 API
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    print("✓ GET /api/status 成功:", data["state"])
    assert "motor_x" in data
    assert "motor_z" in data
    assert "sensors" in data
    assert "electromagnets" in data

    # 2. 測試馬達鎖定 API
    resp = client.post("/api/motor/lock", json={"axis": "ALL", "locked": True})
    assert resp.status_code == 200
    print("✓ POST /api/motor/lock 成功:", resp.json()["message"])

    # 3. 測試寸動 API
    resp = client.post("/api/jog", json={"axis": "X", "direction": 1, "distance": 10.0, "speed": 50.0})
    assert resp.status_code == 200
    print("✓ POST /api/jog 成功")

    # 4. 測試電磁鐵 API
    resp = client.post("/api/electromagnet", json={"channel": 2, "state": True})
    assert resp.status_code == 200
    print("✓ POST /api/electromagnet 成功")

    # 5. 測試設定讀取 API
    resp = client.get("/api/config")
    assert resp.status_code == 200
    cfg = resp.json()
    print("✓ GET /api/config 成功, 步進細分:", cfg["motor_x"]["steps_per_rev"])

    # 6. 測試急停與復歸 API
    resp = client.post("/api/estop")
    assert resp.status_code == 200
    print("✓ POST /api/estop 成功")
    resp = client.post("/api/estop/clear")
    assert resp.status_code == 200
    print("✓ POST /api/estop/clear 成功")

    # 7. 測試前端首頁靜態資源
    resp = client.get("/")
    assert resp.status_code == 200
    assert "雙軸龍門" in resp.text
    print("✓ GET / (前端網頁) 載入成功")

    print("\n===============================")
    print("所有 Web API 路由測試 100% 通過！")
    print("===============================")

if __name__ == "__main__":
    test_api()

