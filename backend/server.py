import os
import asyncio
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import config_mgr, SystemConfig
from .motion_engine import MotionEngine
from .system_manager import SystemManager

logger = logging.getLogger("ControlServer")

# 建立 FastAPI 實例
app = FastAPI(title="雙軸龍門機械手臂智能控制系統", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 核心業務控制器
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
motion_engine = MotionEngine(config_mgr)
system_manager = SystemManager(APP_ROOT)

# WebSocket 連線管理池
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# --- 定義請求結構體 ---
class JogRequest(BaseModel):
    axis: str             # "X" 或 "Z"
    direction: int        # 1 或 -1
    distance: float       # mm
    speed: float = None   # mm/s (選填)

class MoveToRequest(BaseModel):
    x: float = None
    z: float = None
    speed: float = None

class HomingRequest(BaseModel):
    axes: str = "ALL"     # "ALL", "X", "Z"

class MotorLockRequest(BaseModel):
    axis: str = "ALL"     # "ALL", "X", "Z"
    locked: bool          # True (致能鎖定保持扭矩), False (離合釋放)

class ElectromagnetRequest(BaseModel):
    channel: int          # 1, 2, 3, 4
    state: bool           # True (吸附), False (釋放)

class ElectromagnetAllRequest(BaseModel):
    state: bool

class SimSensorToggleRequest(BaseModel):
    sensor_name: str      # 如 "x_left", "arm_1", etc.
    active: bool

# --- RESTful API 路由 ---

@app.get("/api/status")
def get_status():
    telemetry = motion_engine.get_telemetry()
    telemetry["system"] = system_manager.get_system_stats()
    return telemetry

@app.post("/api/jog")
def jog(req: JogRequest):
    success = motion_engine.jog(req.axis, req.direction, req.distance, req.speed)
    if not success:
        raise HTTPException(status_code=400, detail="無法執行寸動 (可能正在運轉或處於警報態)")
    return {"status": "ok", "message": f"{req.axis}軸寸動已啟動"}

@app.post("/api/move_to")
def move_to(req: MoveToRequest):
    success = motion_engine.move_to(x=req.x, z=req.z, speed=req.speed)
    if not success:
        raise HTTPException(status_code=400, detail="無法執行定位移動")
    return {"status": "ok"}

@app.post("/api/homing")
def homing(req: HomingRequest):
    success = motion_engine.start_homing(req.axes)
    if not success:
        raise HTTPException(status_code=400, detail="無法啟動自動歸零程序")
    return {"status": "ok", "message": f"{req.axes} 歸零程序已啟動"}

@app.post("/api/motor/lock")
def set_motor_lock(req: MotorLockRequest):
    motion_engine.set_motor_lock(req.axis, req.locked)
    action = "鎖定致能" if req.locked else "離合釋放"
    return {"status": "ok", "message": f"馬達 {req.axis} 已{action}"}

@app.post("/api/estop")
def emergency_stop():
    motion_engine.emergency_stop()
    return {"status": "ok", "message": "緊急煞車已執行"}

@app.post("/api/estop/clear")
def clear_estop():
    motion_engine.clear_estop()
    return {"status": "ok", "message": "緊急煞車已復歸解除"}

@app.post("/api/electromagnet")
def set_electromagnet(req: ElectromagnetRequest):
    ok = motion_engine.electromagnets.set_channel(req.channel, req.state)
    if not ok:
        raise HTTPException(status_code=400, detail="無效的電磁鐵通道")
    return {"status": "ok", "channel": req.channel, "state": req.state}

@app.post("/api/electromagnet/all")
def set_electromagnet_all(req: ElectromagnetAllRequest):
    motion_engine.electromagnets.set_all(req.state)
    return {"status": "ok", "state": req.state}

@app.get("/api/config")
def get_config():
    return config_mgr.config.model_dump()

@app.post("/api/config")
def update_config(new_cfg: SystemConfig):
    ok = config_mgr.save(new_cfg)
    if not ok:
        raise HTTPException(status_code=500, detail="設定檔寫入失敗")
    motion_engine.reload_config(new_cfg)
    return {"status": "ok", "message": "設定已成功儲存並動態生效"}

@app.get("/api/system/stats")
def get_system_stats():
    return system_manager.get_system_stats()

@app.post("/api/system/update")
def execute_update():
    return system_manager.execute_git_update()

@app.post("/api/system/restart")
def restart_service():
    return system_manager.restart_service()

@app.post("/api/system/reboot")
def reboot_system():
    return system_manager.reboot_system()

@app.post("/api/sim/sensor")
def sim_toggle_sensor(req: SimSensorToggleRequest):
    """供模擬測試時由前端手動點擊切換接近開關狀態"""
    if not motion_engine.is_simulation:
        return {"status": "ignored", "message": "非模擬模式，無法手動覆蓋真實硬體感測器"}
    
    # 查找對應 pin
    sensors = config_mgr.config.sensors
    pin = getattr(sensors, req.sensor_name, None)
    if pin is not None:
        val = 0 if req.active else 1 # active_low
        motion_engine.gpio.set_sim_input(pin, val)
        return {"status": "ok", "sensor": req.sensor_name, "active": req.active}
    return {"status": "error", "message": "找不到感測器引腳名稱"}

# --- WebSocket 高頻遙測推播 ---
@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # 也可以接收前端發來的快捷指令
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.05)
                # 處理即時指令
                cmd = data.get("cmd")
                if cmd == "jog":
                    motion_engine.jog(data.get("axis"), data.get("direction"), data.get("distance"), data.get("speed"))
                elif cmd == "estop":
                    motion_engine.emergency_stop()
            except asyncio.TimeoutError:
                pass
            
            # 推送目前最新遙測封包 (約 15~20Hz)
            telemetry = motion_engine.get_telemetry()
            telemetry["system"] = system_manager.get_system_stats()
            await websocket.send_json(telemetry)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        ws_manager.disconnect(websocket)

# --- 靜態網頁資源掛載 ---
FRONTEND_DIR = os.path.join(APP_ROOT, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
