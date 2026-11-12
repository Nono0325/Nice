# 雙軸龍門機械手臂智能控制系統 (Raspberry Pi 4 專用)

本系統專為配備 **樹梅派 4 (Raspberry Pi 4)**、**2HSS86H 閉環步進伺服驅動器**、**57BYG-112 步進馬達**、**QN-1805-E1 方形電感接近開關 (13顆)** 與 **LSD-P25/20 強力直流電磁鐵 (4組)** 的工業雙軸龍門機台打造。

具備現代化高對比工控 Cockpit 網頁操作介面、高頻 WebSocket 雙向即時遙測、全自動安全防撞歸零程序、馬達致能保持/釋放鎖定、參數動態熱更新與系統線上維護等完整功能。

---

## 🛠️ 硬體組成與規格

* **主控制器**：樹梅派 4 (Raspberry Pi 4 Model B)
* **閉環步進驅動器**：2HSS86H 兩相混合式步進伺服驅動器 * 2 台 (含 ALM 脫步報警回授)
* **步進馬達**：57BYG-112 4.6P SH21 B1-046-LBW * 3 顆 (X 軸 1 顆，Z 軸 2 顆同步並聯驅動)
* **電感式接近開關**：QN-1805-E1 方形接近開關 * 13 顆
  * **X 軸 3 顆**：X_LEFT (原點/左極限), X_MID (中間到位), X_RIGHT (右極限)
  * **Z 軸 2 顆**：Z_UP (頂端安全原點), Z_DOWN (下行程極限)
  * **手臂末端 8 顆**：ARM_1 ~ ARM_8 (工件定位與夾爪檢測)
* **直流電磁鐵**：LSD-P25/20 圓形強力直流電磁鐵 * 4 組 (獨立吸附/釋放控制)
* **隔離保護模組**：817 光耦電壓隔離板 & PC817 電壓控制轉接模組 (保護樹梅派 GPIO 3.3V)

---

## 🚀 六大核心功能

1. **📱 現代化控制頁面 (Responsive Cockpit Web UI)**
   * 直覺十字方向寸動控制台 (Jog)，支援 0.1mm / 1mm / 5mm / 10mm / 50mm / 100mm 步長切換。
   * 慢速微調 (15mm/s)、標準定位 (50mm/s)、快速巡航 (100mm/s) 速度預設。
   * 絕對座標定位移動 (G0/G1 模式)，一鍵精確直達指定座標。
   * 電磁鐵專用控制面板，支援 1~4 號單獨點動切換或全部一鍵吸附/斷電。
   * 大按鈕硬體級「🛑 緊急停止 (E-STOP)」與「重置復歸」機制。

2. **📊 即時全狀態顯示 (Real-Time Telemetry & Status)**
   * 雙軸毫米座標、脈衝累計步數、行程百分比進度條與歸零校準狀態標籤。
   * 13 顆接近開關與 2 組閉環警報 (ALM) 即時狀態矩陣。
   * 手臂末端 8 點工件感測 LED 即時視覺化面板。
   * 樹梅派主機 CPU 溫度、CPU 負載、記憶體使用量、系統運作時間與通訊延遲監控。
   * 系統運作與故障事件控制台日誌 (Console Log)。

3. **🔄 全自動防撞歸零 (Auto Homing Routine)**
   * 智慧安全歸零順序：**先將 Z 垂直軸升起至頂端 Z_UP 接近開關避碰**，退回緩衝距後以二次慢速精碰校準原點；接著再將 **X 水平軸向左平移至 X_LEFT 接近開關** 校準原點。
   * 支援「全軸自動歸零」、「僅歸零 Z 軸」、「僅歸零 X 軸」。

4. **🔒 馬達致能鎖定 (Motor Enable / Lock)**
   * 支援硬體 ENA 引腳信號切換。
   * **鎖定致能**：馬達通電保持強大靜態保持力矩，防止垂直軸負載下墜或外力位移。
   * **離合釋放**：關閉線圈激磁電流，允許操作人員手動推動滑台與調整機構。
   * 具備軟體安全聯鎖，未致能時禁止執行運動指令。

5. **⚙️ 馬達設定 (Dynamic Motor Settings)**
   * 網頁線上直接調整微步細分 (Steps/Rev)、螺桿導程 (Pitch mm/Rev)、最高速度、尋點速度、二次觸碰精確速度、加速度。
   * 軟體行程邊界限制 (Min/Max Limits)，超越邊界自動阻斷防撞。
   * 方向信號反轉 (Dir Invert)、致能極性反轉 (Ena Invert)、歸零方向與原點偏移量自定義。
   * 一鍵儲存並動態熱生效 (免重啟後端程式)。

6. **🔄 系統更新與維護 (System Maintenance & Update)**
   * 線上一鍵 Git 更新 (Git Pull 最新程式碼)。
   * 一鍵重啟 Linux 系統守護行程 (`systemctl restart gantry-control`)。
   * 樹梅派主機遠端重開機與安全關機。

---

## ⚡ 快速安裝與樹梅派開機自啟

### 1. 於樹梅派 4 設定開機自動啟動 (Auto-Start on Boot)
若希望**樹梅派一通電開機就自動在背景執行控制系統**，直接執行專用腳本：
```bash
chmod +x scripts/setup-autostart.sh
./scripts/setup-autostart.sh
```
此腳本會自動：
* 偵測當前使用者與工作目錄，自動註冊 `gantry-control.service` 至 `systemd`。
* 啟用開機自啟 (`systemctl enable`) 並立即啟動服務。
* 今後斷電重啟或開機，系統將自動啟動運行，免手動登入下指令！

常用服務維護指令：
```bash
sudo systemctl status gantry-control   # 查看運作狀態
sudo systemctl restart gantry-control  # 重啟服務
sudo systemctl stop gantry-control     # 停止服務
sudo journalctl -u gantry-control -f   # 即時查看運作日誌
```

#### (選用) 觸控螢幕開機全螢幕顯示 (Kiosk Mode)
若機台上裝有 7 吋 / 10 吋觸控螢幕或 HDMI 螢幕，可執行：
```bash
chmod +x scripts/setup-kiosk-autostart.sh
./scripts/setup-kiosk-autostart.sh
```
開機進入桌面後，系統將自動以全螢幕 Chromium 顯示控制面板。

---

### 2. 開啟控制頁面
使用同區域網路內的任何電腦、手機、平板或樹梅派本機螢幕開啟瀏覽器：
```
http://<樹梅派IP>:8000
```
*(例如：`http://192.168.1.100:8000` 或本機 `http://localhost:8000`)*

---

## 💻 支援跨平台模擬模式 (Simulation Mode)

本系統具備自動硬體抽象層 (HAL)：
* 當於 **樹梅派 4** 執行時，自動調用真實硬體 GPIO 與高頻脈衝。
* 當於 **Windows / Mac / PC 開發測試** 時，系統會自動切換為 **虛擬模擬模式 (Simulation Mode)**，可在無實體硬體的情況下直接於瀏覽器模擬測試馬達運動、點擊感測器與驗證自動歸零邏輯！

本機手動啟動：
```bash
python main.py
```

---

## 📖 相關文件

* 完整電氣接線圖與 GPIO 引腳分配手冊：請參閱 [docs/WIRING_DIAGRAM.md](file:///c:/Nono/Nice2/docs/WIRING_DIAGRAM.md)
* 系統設定檔：[config.json](file:///c:/Nono/Nice2/config.json)
