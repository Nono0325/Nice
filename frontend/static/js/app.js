// 雙軸龍門控制系統前端邏輯 (Vue 3 輕量響應式架構)
const { createApp, ref, reactive, computed, onMounted, onUnmounted } = Vue;

createApp({
  setup() {
    // 導航分頁
    const currentTab = ref('cockpit'); // cockpit, sensors, motors, system

    // 即時遙測數據 (由 WebSocket 頻繁更新)
    const telemetry = reactive({
      state: 'IDLE',
      is_simulation: false,
      motor_x: {
        name: 'X軸馬達',
        position_mm: 0.0,
        position_steps: 0,
        is_locked: true,
        is_moving: false,
        is_homed: false,
        steps_per_mm: 40.0,
        max_speed: 120.0,
        min_limit_mm: 0.0,
        max_limit_mm: 600.0
      },
      motor_z: {
        name: 'Z軸馬達',
        position_mm: 0.0,
        position_steps: 0,
        is_locked: true,
        is_moving: false,
        is_homed: false,
        steps_per_mm: 320.0,
        max_speed: 40.0,
        min_limit_mm: 0.0,
        max_limit_mm: 300.0
      },
      sensors: {
        x_left: false,
        x_mid: false,
        x_right: false,
        z_up: false,
        z_down: false,
        arm_1: false, arm_2: false, arm_3: false, arm_4: false,
        arm_5: false, arm_6: false, arm_7: false, arm_8: false,
        x_alm: false,
        z_alm: false,
        summary: {
          x_limits: { left: false, mid: false, right: false },
          z_limits: { up: false, down: false },
          arm_sensors: [false, false, false, false, false, false, false, false],
          alarms: { x_alm: false, z_alm: false }
        }
      },
      electromagnets: {
        em1: false,
        em2: false,
        em3: false,
        em4: false,
        any_active: false
      },
      system: {
        cpu_percent: 0,
        cpu_temp_c: 0,
        ram_used_mb: 0,
        ram_total_mb: 0,
        ram_percent: 0,
        disk_percent: 0,
        uptime: '--',
        platform: '--',
        python_version: '--'
      }
    });

    // 運動控制參數
    const jogDistance = ref(10.0); // 預設寸動 10mm
    const jogSpeed = ref(30.0);    // 預設寸動速度 30 mm/s
    const customTargetX = ref(0.0);
    const customTargetZ = ref(0.0);

    // 系統日誌
    const logs = ref([]);
    const addLog = (msg, type = 'info') => {
      const timeStr = new Date().toLocaleTimeString();
      logs.value.unshift({ time: timeStr, text: msg, type });
      if (logs.value.length > 50) logs.value.pop();
    };

    // WebSocket 連線
    let ws = null;
    const wsConnected = ref(false);

    const initWebSocket = () => {
      const loc = window.location;
      const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${loc.host}/ws/telemetry`;

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        wsConnected.value = true;
        addLog('即時遙測 WebSocket 連線建立成功', 'info');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          Object.assign(telemetry, data);
        } catch (e) {
          console.error('解析遙測失敗', e);
        }
      };

      ws.onclose = () => {
        wsConnected.value = false;
        setTimeout(initWebSocket, 2000); // 斷線自動重試
      };

      ws.onerror = (err) => {
        console.error('WS 發生錯誤', err);
      };
    };

    // --- API 呼叫 ---
    const sendJog = async (axis, dir) => {
      const dist = parseFloat(jogDistance.value);
      const speed = Math.max(1.0, parseFloat(jogSpeed.value) || 20.0);
      try {
        const res = await fetch('/api/jog', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            axis,
            direction: dir,
            distance: dist,
            speed
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '寸動失敗');
        addLog(`觸發 ${axis} 軸寸動: ${dir > 0 ? '+' : '-'}${dist}mm (${speed}mm/s)`, 'info');
      } catch (err) {
        addLog(`寸動失敗: ${err.message}`, 'err');
      }
    };

    const moveToCustom = async () => {
      try {
        const x = parseFloat(customTargetX.value);
        const z = parseFloat(customTargetZ.value);
        const res = await fetch('/api/move_to', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ x, z })
        });
        if (!res.ok) throw new Error('定位指令拒絕');
        addLog(`目標定位開始: X=${x}mm, Z=${z}mm`, 'info');
      } catch (err) {
        addLog(`定位錯誤: ${err.message}`, 'err');
      }
    };

    // 自動歸零
    const triggerHoming = async (axes = 'ALL') => {
      const axisName = axes === 'ALL' ? '全軸 (Z先升後X)' : `${axes}軸`;
      if (!confirm(`確定要啟動 ${axisName} 自動歸零程序嗎？\n請確認工作區無異物阻擋。`)) return;
      try {
        const res = await fetch('/api/homing', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ axes })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '歸零啟動失敗');
        addLog(`已啟動 ${axisName} 自動復歸原點程序`, 'info');
      } catch (err) {
        addLog(`歸零失敗: ${err.message}`, 'err');
      }
    };

    // 馬達致能鎖定
    const toggleMotorLock = async (axis) => {
      let currentLocked = true;
      if (axis === 'X') currentLocked = telemetry.motor_x.is_locked;
      else if (axis === 'Z') currentLocked = telemetry.motor_z.is_locked;
      else currentLocked = telemetry.motor_x.is_locked && telemetry.motor_z.is_locked;

      const targetLock = !currentLocked;
      const actionName = targetLock ? '鎖定 (保持力矩)' : '釋放 (手動移動)';

      try {
        const res = await fetch('/api/motor/lock', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ axis, locked: targetLock })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        addLog(`${axis} 軸馬達致能已切換為: ${actionName}`, 'info');
      } catch (err) {
        addLog(`馬達致能設定失敗: ${err.message}`, 'err');
      }
    };

    // 電磁鐵控制
    const toggleElectromagnet = async (channel) => {
      const current = telemetry.electromagnets[`em${channel}`];
      const targetState = !current;
      try {
        const res = await fetch('/api/electromagnet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ channel, state: targetState })
        });
        if (!res.ok) throw new Error('控制失敗');
        addLog(`電磁鐵 EM${channel} -> ${targetState ? '吸附' : '關閉'}`, 'info');
      } catch (err) {
        addLog(`電磁鐵控制失敗: ${err.message}`, 'err');
      }
    };

    const toggleAllElectromagnets = async (state) => {
      try {
        const res = await fetch('/api/electromagnet/all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state })
        });
        if (!res.ok) throw new Error('控制失敗');
        addLog(`全部電磁鐵 -> ${state ? '全部吸附' : '全部斷電'}`, 'info');
      } catch (err) {
        addLog(`電磁鐵整體控制失敗: ${err.message}`, 'err');
      }
    };

    // 緊急停止
    const triggerEStop = async () => {
      try {
        await fetch('/api/estop', { method: 'POST' });
        addLog('【緊急煞車】已立即中斷所有軸向運轉！', 'err');
      } catch (err) {
        console.error(err);
      }
    };

    const clearEStop = async () => {
      try {
        await fetch('/api/estop/clear', { method: 'POST' });
        addLog('緊急停止已重置復歸，系統回到待機態', 'info');
      } catch (err) {
        console.error(err);
      }
    };

    // 模擬模式手動觸發感測器測試
    const toggleSimSensor = async (sensorName) => {
      if (!telemetry.is_simulation) return;
      const current = telemetry.sensors[sensorName];
      try {
        await fetch('/api/sim/sensor', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sensor_name: sensorName, active: !current })
        });
        addLog(`[模擬] 手動切換感測器 ${sensorName} -> ${!current ? '觸發' : '復歸'}`, 'info');
      } catch (e) {
        console.error(e);
      }
    };

    // --- 馬達參數設定管理 ---
    const configForm = ref(null);
    const loadConfig = async () => {
      try {
        const res = await fetch('/api/config');
        configForm.value = await res.json();
      } catch (err) {
        addLog(`讀取設定檔失敗: ${err.message}`, 'err');
      }
    };

    const saveConfig = async () => {
      if (!confirm('確認儲存並立即套用新的馬達與系統設定？')) return;
      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(configForm.value)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        addLog('馬達設定已成功儲存並動態更新！', 'info');
      } catch (err) {
        addLog(`儲存設定失敗: ${err.message}`, 'err');
      }
    };

    // --- 系統更新維護 ---
    const isUpdating = ref(false);
    const updateResult = ref('');

    const runGitUpdate = async () => {
      if (!confirm('即將執行 git pull 線上檢查並拉取最新程式碼？')) return;
      isUpdating.value = true;
      updateResult.value = '正在拉取更新...';
      try {
        const res = await fetch('/api/system/update', { method: 'POST' });
        const data = await res.json();
        updateResult.value = data.message || (data.success ? '更新完畢' : '更新失敗');
        addLog(`系統更新執行: ${updateResult.value}`, data.success ? 'info' : 'warn');
      } catch (err) {
        updateResult.value = `更新失敗: ${err.message}`;
        addLog(updateResult.value, 'err');
      } finally {
        isUpdating.value = false;
      }
    };

    const runServiceRestart = async () => {
      if (!confirm('確定重啟後端服務 (gantry-control.service) 嗎？\n連線將暫時中斷 3 秒。')) return;
      try {
        const res = await fetch('/api/system/restart', { method: 'POST' });
        const data = await res.json();
        addLog(data.message, 'info');
      } catch (err) {
        addLog(`服務重啟請求失敗: ${err.message}`, 'err');
      }
    };

    const runReboot = async () => {
      if (!confirm('警告：確定要重新啟動樹梅派主機嗎？')) return;
      try {
        const res = await fetch('/api/system/reboot', { method: 'POST' });
        const data = await res.json();
        addLog(data.message, 'warn');
      } catch (err) {
        addLog(`重開機失敗: ${err.message}`, 'err');
      }
    };

    const runShutdown = async () => {
      if (!confirm('🛑 警告：確定要將樹梅派主機安全關機嗎？\n關機後若需重新啟動，需手動重新插拔電源！')) return;
      try {
        const res = await fetch('/api/system/shutdown', { method: 'POST' });
        const data = await res.json();
        addLog(data.message, 'err');
        alert('樹梅派主機關機指令已下達，系統正在安全關閉電源...');
      } catch (err) {
        addLog(`關機請求失敗: ${err.message}`, 'err');
      }
    };

    // 計算 X 軸和 Z 軸的行程進度百分比 (用於條狀指示)
    const xProgressPercent = computed(() => {
      const min = telemetry.motor_x.min_limit_mm;
      const max = telemetry.motor_x.max_limit_mm;
      const cur = telemetry.motor_x.position_mm;
      if (max <= min) return 0;
      return Math.min(100, Math.max(0, ((cur - min) / (max - min)) * 100));
    });

    const zProgressPercent = computed(() => {
      const min = telemetry.motor_z.min_limit_mm;
      const max = telemetry.motor_z.max_limit_mm;
      const cur = telemetry.motor_z.position_mm;
      if (max <= min) return 0;
      return Math.min(100, Math.max(0, ((cur - min) / (max - min)) * 100));
    });

    onMounted(() => {
      initWebSocket();
      loadConfig();
      addLog('控制系統前端初始化就緒', 'info');
    });

    onUnmounted(() => {
      if (ws) ws.close();
    });

    return {
      currentTab,
      telemetry,
      wsConnected,
      jogDistance,
      jogSpeed,
      customTargetX,
      customTargetZ,
      logs,
      configForm,
      isUpdating,
      updateResult,
      xProgressPercent,
      zProgressPercent,
      sendJog,
      moveToCustom,
      triggerHoming,
      toggleMotorLock,
      toggleElectromagnet,
      toggleAllElectromagnets,
      triggerEStop,
      clearEStop,
      toggleSimSensor,
      saveConfig,
      runGitUpdate,
      runServiceRestart,
      runReboot,
      runShutdown
    };
  }
}).mount('#app');

