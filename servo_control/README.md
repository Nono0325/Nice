# 🤖 樹梅派伺服馬達控制系統

> **衝壓機自動化搬運系統** — Raspberry Pi X/Y 軸伺服馬達控制 + 即時網頁監控

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)](https://flask.palletsprojects.com)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-GPIO-red?logo=raspberry-pi)](https://www.raspberrypi.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ⚡ 一鍵安裝（樹梅派）

SSH 連線到樹梅派後，執行以下**任一指令**即可完成安裝＋設定開機自動執行：

```bash
# 方式一：curl
curl -fsSL https://raw.githubusercontent.com/Nono0325/Nice/main/servo_control/install.sh | sudo bash

# 方式二：wget
wget -qO- https://raw.githubusercontent.com/Nono0325/Nice/main/servo_control/install.sh | sudo bash
```

安裝完成後，**瀏覽器開啟** `http://<樹梅派IP>:5000` 即可使用。

---

## 🖥️ Windows / PC 本地測試

```bash
git clone https://github.com/Nono0325/Nice.git
cd Nice/servo_control
pip install flask flask-socketio eventlet
python servo_controller.py
```

瀏覽器開啟：http://localhost:5000

---

## 📸 介面預覽

| 控制面板（仿 PPT 設計） | 訊號檢測（PWM 波形） |
|---|---|
| START_PB/STOP_PB 金屬按鈕 | 即時 Chart.js 波形圖 |
| 6 顆狀態指示燈 | Pulse Width / Duty Cycle 數值 |
| LEFT-IDLE-RIGHT 位置條 | X / Y1 / Y2 三軸分開顯示 |

---

## 🔌 硬體接線（BCM 編號）

| 功能 | GPIO | 實體腳位 | 說明 |
|------|------|----------|------|
| **X 軸馬達** | GPIO 12 | Pin 32 | Hardware PWM0 |
| **Y1 軸馬達** | GPIO 13 | Pin 33 | Hardware PWM1 |
| **Y2 軸馬達** | GPIO 18 | Pin 12 | Hardware PWM0 (ALT) |
| **吸盤繼電器** | GPIO 24 | Pin 18 | 數位輸出 HIGH=ON |
| **Z_DOWN 繼電器** | GPIO 25 | Pin 22 | 數位輸出 HIGH=ON |
| **限位 LEFT** | GPIO 17 | Pin 11 | INPUT_PULLUP（觸發=LOW） |
| **限位 RIGHT** | GPIO 27 | Pin 13 | INPUT_PULLUP |
| **限位 UP** | GPIO 22 | Pin 15 | INPUT_PULLUP |
| **限位 DOWN** | GPIO 23 | Pin 16 | INPUT_PULLUP |
| GND | GND | Pin 6/9 | 接地 |
| 5V | 5V | Pin 2/4 | 馬達電源（建議外接） |

> ⚠️ 伺服馬達電流需求較大，建議使用**外部 5V 電源**供電，不要從 Pi GPIO 直接取電。

---

## 📐 PWM 規格

| 參數 | 數值 |
|------|------|
| 頻率 | **50 Hz** |
| 週期 | 20 ms |
| 最小脈衝（LEFT/DOWN） | **500 µs** → 2.5% Duty |
| 中心位置（IDLE） | **1500 µs** → 7.5% Duty |
| 最大脈衝（RIGHT/UP） | **2500 µs** → 12.5% Duty |

---

## 🎮 網頁介面功能（5 個 Tab）

### 1️⃣ 控制面板
- **START_PB / STOP_PB** 金屬質感按鈕（仿工業 HMI）
- 6 顆圓形指示燈：Start Pickup / Arm Down / Vacuum / Lim LEFT / Lim RIGHT / Error
- **X 軸位置條**（LEFT ← IDLE → RIGHT，可拖曳）
- **Y 軸位置條**（DOWN ← MIDDLE → UP，可拖曳）
- 方向按鈕 + 步進值選擇（10 / 50 / 100 / 200 µs）
- Arm Down / Vacuum 切換按鈕
- 🔄 **自動取件流程**（X 移動 → 手臂下 → 吸盤 → 搬運 → 放置 → 歸零）

### 2️⃣ 即時監控
- X / Y1 / Y2 三軸量規儀表（Canvas 繪製）
- 數位輸出狀態（VACUUM / Z_DOWN）
- 限位開關狀態（LEFT / RIGHT / UP / DOWN）
- 系統即時日誌

### 3️⃣ 訊號檢測
- 即時 **PWM 波形圖**（X 軸 + Y1/Y2 軸分別顯示）
- 當前 Pulse Width（µs）+ Duty Cycle（%）數值表
- PWM 參數說明卡片

### 4️⃣ 範圍設定
- X 軸最大/最小行程設定（µs 滑桿）
- Y 軸最大/最小行程設定（µs 滑桿）
- Y1 / Y2 同步模式開關
- GPIO 引腳對應圖

### 5️⃣ 馬達診斷
- GPIO 模式顯示（Real GPIO / Simulation）
- 馬達掃描測試（X / Y 軸）
- Vacuum 測試
- 即時診斷日誌

---

## ⌨️ 鍵盤快捷鍵

| 按鍵 | 功能 |
|------|------|
| `←` `→` | X 軸左/右移動 |
| `↑` `↓` | Y 軸上/下移動 |
| `V` | 吸盤切換 |
| `Z` | 手臂切換 |
| `H` | 全部歸零 |

---

## 🔧 系統管理指令

```bash
# 查看服務狀態
sudo systemctl status servo-control

# 查看即時日誌
sudo journalctl -u servo-control -f

# 重啟服務
sudo systemctl restart servo-control

# 停止服務
sudo systemctl stop servo-control

# 關閉開機自動執行
sudo systemctl disable servo-control

# 更新程式（需先 git pull）
cd /home/pi/servo_control
git pull
sudo systemctl restart servo-control
```

---

## 📁 目錄結構

```
servo_control/
├── install.sh              ← 🚀 一鍵安裝腳本（含開機自動執行）
├── servo_controller.py     ← 後端主程式（Flask + SocketIO + GPIO）
├── requirements.txt        ← Python 依賴
├── start.sh               ← 手動啟動腳本
├── README.md              ← 本文件
├── .gitignore
├── templates/
│   └── index.html         ← 網頁介面（5個Tab）
└── static/
    ├── css/style.css      ← 工業深色主題樣式
    └── js/app.js          ← 前端 JavaScript
```

---

## 🍓 開機自動執行原理

安裝腳本會建立 `/etc/systemd/system/servo-control.service`，使系統在網路就緒後自動啟動控制程式。設定如下：

- **自動重啟**：若程式崩潰，5 秒後自動重啟
- **依賴服務**：在 `network.target` 和 `pigpiod.service` 之後啟動
- **日誌整合**：可透過 `journalctl` 查看完整日誌

---

## 🛠️ 手動開機自啟設定（進階）

若一鍵安裝失敗，可手動設定：

```bash
sudo nano /etc/systemd/system/servo-control.service
```

貼上以下內容（修改路徑）：

```ini
[Unit]
Description=樹梅派伺服馬達控制系統
After=network.target pigpiod.service

[Service]
User=pi
WorkingDirectory=/home/pi/servo_control
ExecStart=/home/pi/servo_control/venv/bin/python /home/pi/servo_control/servo_controller.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable servo-control
sudo systemctl start servo-control
```

---

## 📄 License

MIT License — 歡迎自由使用與修改
