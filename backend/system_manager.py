import os
import sys
import time
import subprocess
import logging
import psutil
from typing import Dict, Any

logger = logging.getLogger("SystemManager")

class SystemManager:
    """
    維護樹梅派主機硬體狀態監控、系統更新、服務重啟與電源控制
    """
    def __init__(self, app_dir: str):
        self.app_dir = app_dir
        self.boot_time = psutil.boot_time()

    def get_system_stats(self) -> Dict[str, Any]:
        # CPU 溫度 (樹梅派特有路徑: /sys/class/thermal/thermal_zone0/temp)
        cpu_temp = 0.0
        try:
            if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    cpu_temp = float(f.read().strip()) / 1000.0
            else:
                # 模擬環境或 Windows 平台
                temps = getattr(psutil, "sensors_temperatures", lambda: {})()
                if temps:
                    for name, entries in temps.items():
                        if entries:
                            cpu_temp = entries[0].current
                            break
                if cpu_temp == 0.0:
                    cpu_temp = 42.5  # 模擬正常工作溫度
        except Exception:
            cpu_temp = 42.0

        # 記憶體與磁碟
        mem = psutil.virtual_memory()
        disk_percent = 0.0
        try:
            path = "/" if os.name != "nt" else os.path.splitdrive(os.path.abspath("."))[0] + "\\"
            disk = psutil.disk_usage(path)
            disk_percent = disk.percent
        except Exception:
            disk_percent = 50.0

        # 運作時間 (Uptime)
        uptime_sec = int(time.time() - self.boot_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}時 {minutes}分 {seconds}秒"

        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cpu_temp_c": round(cpu_temp, 1),
            "ram_used_mb": round((mem.total - mem.available) / (1024 * 1024), 1),
            "ram_total_mb": round(mem.total / (1024 * 1024), 1),
            "ram_percent": mem.percent,
            "disk_percent": disk_percent,
            "uptime": uptime_str,
            "platform": sys.platform,
            "python_version": sys.version.split()[0]
        }

    def execute_git_update(self) -> Dict[str, Any]:
        """從 Git 倉庫拉取最新程式碼更新"""
        try:
            res = subprocess.run(["git", "pull"], cwd=self.app_dir, capture_output=True, text=True, timeout=30)
            return {
                "success": res.returncode == 0,
                "message": res.stdout if res.returncode == 0 else res.stderr,
                "code": res.returncode
            }
        except Exception as e:
            return {"success": False, "message": f"執行 git pull 失敗: {str(e)}", "code": -1}

    def restart_service(self) -> Dict[str, Any]:
        """重啟 systemd 守護服務 (gantry-control.service)"""
        if os.name == "nt":
            return {"success": True, "message": "Windows 平台已模擬重啟服務信號"}
        try:
            res = subprocess.run(["sudo", "systemctl", "restart", "gantry-control.service"], capture_output=True, text=True, timeout=10)
            return {
                "success": res.returncode == 0,
                "message": "服務重啟指令已送出" if res.returncode == 0 else res.stderr
            }
        except Exception as e:
            return {"success": False, "message": f"重啟服務失敗: {str(e)}"}

    def reboot_system(self) -> Dict[str, Any]:
        """重開機樹梅派"""
        if os.name == "nt":
            return {"success": True, "message": "Windows 平台模擬主機重啟指令"}
        try:
            subprocess.Popen(["sudo", "reboot"])
            return {"success": True, "message": "樹梅派重開機指令已下達"}
        except Exception as e:
            return {"success": False, "message": f"重開機失敗: {str(e)}"}

    def shutdown_system(self) -> Dict[str, Any]:
        """安全關閉樹梅派主機電源 (sudo shutdown -h now)"""
        if os.name == "nt":
            return {"success": True, "message": "Windows 平台模擬安全關機指令"}
        try:
            subprocess.Popen(["sudo", "shutdown", "-h", "now"])
            return {"success": True, "message": "樹梅派安全關機指令已下達，系統即將關閉電源"}
        except Exception as e:
            return {"success": False, "message": f"關機失敗: {str(e)}"}
