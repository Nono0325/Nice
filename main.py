import uvicorn
import logging
import sys
import os

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Main")

def main():
    logger.info("==========================================================")
    logger.info("  雙軸龍門機械手臂智能控制系統 (Raspberry Pi 4 專用)")
    logger.info("  配備: 2HSS86H閉環驅動*2 / 57BYG步進*3 / QN-1805-E1*13 / LSD-P25/20*4")
    logger.info("==========================================================")

    # 讀取設定
    from backend.config import config_mgr
    cfg = config_mgr.config
    
    logger.info(f"伺服器即將在 http://{cfg.web_host}:{cfg.web_port} 啟動...")
    uvicorn.run("backend.server:app", host=cfg.web_host, port=cfg.web_port, reload=False, access_log=False)

if __name__ == "__main__":
    main()
