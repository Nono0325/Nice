/**
 * 樹梅派伺服馬達控制系統 - 前端 JavaScript
 * Raspberry Pi Servo Motor Controller - Frontend App
 */

// ── WebSocket 連線 ──────────────────────────────────────────────
const socket = io({ transports: ['websocket', 'polling'] });

// ── 全域狀態 ──────────────────────────────────────────────────
let state = {
  x_pulse: 1500, y1_pulse: 1500, y2_pulse: 1500,
  x_pct: 50, y_pct: 50,
  vacuum: false, z_down: false,
  system_run: false, arm_down: false,
  pickup_active: false, error: false, error_msg: '',
  lim_left: false, lim_right: false, lim_up: false, lim_down: false,
  x_min: 500, x_max: 2500, y_min: 500, y_max: 2500,
  y_sync: true,
  x_scale: 10.0, y_scale: 10.0,
  x_max_speed: 2000.0, x_accel_steps: 100.0,
  y_max_speed: 2000.0, y_accel_steps: 100.0,
  motor_locked: true,
  timestamp: '',
  gpio_mode: '-'
};

let stepSize  = 50;       // 步進值 µs
let isTestRunning = false;
let testInterval = null;

// ── Chart.js 圖表 ────────────────────────────────────────────
let chartX = null, chartY = null;

function initCharts() {
  const labels = Array.from({ length: 60 }, (_, i) => '');
  const chartConfig = (labels, datasets) => ({
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: {
          min: 400, max: 2600,
          grid: { color: 'rgba(42,58,85,0.4)', drawBorder: false },
          ticks: {
            color: '#475569', font: { family: "'JetBrains Mono'" , size: 10 },
            callback: v => v + 'µs'
          }
        }
      },
      elements: { point: { radius: 0 }, line: { tension: 0.3, borderWidth: 2 } }
    }
  });

  const ctxX = document.getElementById('chartX')?.getContext('2d');
  if (ctxX) {
    chartX = new Chart(ctxX, chartConfig(labels, [{
      label: 'X Motor', data: new Array(60).fill(1500),
      borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.06)',
      fill: true
    }]));
  }

  const ctxY = document.getElementById('chartY')?.getContext('2d');
  if (ctxY) {
    chartY = new Chart(ctxY, chartConfig(labels, [
      { label: 'Y1 Motor', data: new Array(60).fill(1500), borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.04)', fill: false },
      { label: 'Y2 Motor', data: new Array(60).fill(1500), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.04)', fill: false }
    ]));
  }
}

// ── 量規繪製 ─────────────────────────────────────────────────
function drawGauge(canvasId, value, min, max, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const r  = cx - 12;
  const startAngle = Math.PI * 0.75;
  const endAngle   = Math.PI * 2.25;
  const pct = (value - min) / (max - min);
  const valAngle = startAngle + pct * (endAngle - startAngle);

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 背景弧
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, endAngle);
  ctx.strokeStyle = '#1a2235';
  ctx.lineWidth = 12;
  ctx.lineCap = 'round';
  ctx.stroke();

  // 刻度弧
  const grad = ctx.createLinearGradient(0, 0, canvas.width, 0);
  grad.addColorStop(0, '#ef4444');
  grad.addColorStop(0.5, color);
  grad.addColorStop(1, '#10b981');
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, valAngle);
  ctx.strokeStyle = grad;
  ctx.lineWidth = 12;
  ctx.lineCap = 'round';
  ctx.stroke();

  // 刻度標記
  for (let i = 0; i <= 10; i++) {
    const a = startAngle + (i / 10) * (endAngle - startAngle);
    const inner = r - 18, outer = r - 6;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
    ctx.lineTo(cx + Math.cos(a) * outer, cy + Math.sin(a) * outer);
    ctx.strokeStyle = i % 5 === 0 ? 'rgba(148,163,184,0.6)' : 'rgba(71,85,105,0.4)';
    ctx.lineWidth = i % 5 === 0 ? 2 : 1;
    ctx.stroke();
  }

  // 指針
  const needleLen = r - 22;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(valAngle) * needleLen, cy + Math.sin(valAngle) * needleLen);
  ctx.strokeStyle = '#f8fafc';
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  ctx.stroke();

  // 中心圓
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();

  // 數值文字
  ctx.font = "bold 13px 'JetBrains Mono'";
  ctx.fillStyle = 'rgba(148,163,184,0.6)';
  ctx.textAlign = 'center';
  ctx.fillText(`${Math.round(pct * 100)}%`, cx, cy + r * 0.55);
}

// ── WebSocket 事件 ───────────────────────────────────────────
socket.on('connect', () => {
  console.log('[WS] Connected');
  setWsStatus(true);
  addLog('WebSocket 已連線', 'success');
  updateDiagWsTag(true);
});

socket.on('disconnect', () => {
  setWsStatus(false);
  addLog('WebSocket 已斷線', 'error');
  updateDiagWsTag(false);
});

socket.on('state_update', (data) => {
  state = { ...state, ...data };
  updateUI();
  if (typeof update3D === 'function') {
    update3D(state);
  }
});

function setWsStatus(online) {
  const dot  = document.getElementById('wsStatusDot');
  const text = document.getElementById('wsStatusText');
  if (dot)  dot.className = 'status-dot' + (online ? ' online' : '');
  if (text) text.textContent = online ? '已連線' : '已斷線';
}

function updateDiagWsTag(online) {
  const el = document.getElementById('ws-status-tag');
  if (!el) return;
  el.className = `tag ${online ? 'tag-green' : 'tag-red'}`;
  el.textContent = online ? '✔ 已連線' : '✘ 已斷線';
}

// ── UI 更新 ─────────────────────────────────────────────────
function updateUI() {
  const s = state;

  // 時鐘
  document.getElementById('systemTimestamp').textContent = s.timestamp || '--:--:--';
  document.getElementById('gpioModeText').textContent = s.gpio_mode || '-';

  // START / STOP 按鈕
  const btnStart = document.getElementById('btnStart');
  const btnStop  = document.getElementById('btnStop');
  const sysText  = document.getElementById('systemStatusText');
  if (s.system_run) {
    btnStart?.classList.add('active');
    btnStop?.classList.remove('active');
    if (sysText) { sysText.textContent = '▶ RUNNING'; sysText.style.color = 'var(--accent-green)'; }
  } else {
    btnStart?.classList.remove('active');
    btnStop?.classList.add('active');
    if (sysText) { sysText.textContent = '■ STOPPED'; sysText.style.color = 'var(--accent-red)'; }
  }

  // 指示燈
  setLamp('lamp-pickup',  s.pickup_active ? 'amber' : 'off');
  setLamp('lamp-armdown', s.arm_down      ? 'amber' : 'off');
  setLamp('lamp-vacuum',  s.vacuum        ? 'amber' : 'off');
  setLamp('lamp-limleft',  s.lim_left  ? 'red' : 'off');
  setLamp('lamp-limright', s.lim_right ? 'red' : 'off');
  setLamp('lamp-error',    s.error     ? 'red' : 'off');

  // 錯誤橫幅
  const errBanner = document.getElementById('errorBanner');
  if (errBanner) {
    if (s.error) {
      errBanner.classList.add('visible');
      document.getElementById('errorMsg').textContent = s.error_msg || '系統錯誤';
    } else {
      errBanner.classList.remove('visible');
    }
  }

  // X 軸位置條
  const xPct = Math.max(0, Math.min(100, s.x_pct || 0));
  setEl('xBar', el => el.style.width = `${xPct}%`);
  setEl('xPctDisplay', el => el.textContent = `${xPct.toFixed(1)}%`);
  setEl('xPulseDisplay', el => el.textContent = `${s.x_pulse} µs`);
  const xSlider = document.getElementById('xSlider');
  if (xSlider && document.activeElement !== xSlider) xSlider.value = xPct;

  // 真實物理距離 (mm)
  const xScale = s.x_scale || 10.0;
  const yScale = s.y_scale || 10.0;
  const xMm = (s.x_pulse - 500) / xScale;
  setEl('xMmDisplay', el => el.textContent = `${xMm.toFixed(1)} mm`);

  // Y 軸位置條
  const yPct = Math.max(0, Math.min(100, s.y_pct || 0));
  setEl('yBar', el => el.style.width = `${yPct}%`);
  setEl('yPctDisplay', el => el.textContent = `${yPct.toFixed(1)}%`);
  setEl('y1PulseDisplay', el => el.textContent = `${s.y1_pulse} µs`);
  setEl('y2PulseDisplay', el => el.textContent = `${s.y2_pulse} µs`);
  const yMm = (s.y1_pulse - 500) / yScale;
  setEl('yMmDisplay', el => el.textContent = `${yMm.toFixed(1)} mm`);
  
  const ySlider = document.getElementById('ySlider');
  if (ySlider && document.activeElement !== ySlider) ySlider.value = yPct;

  // 進階設定輸入值綁定
  setElValue('xMaxSpeedInput', s.x_max_speed || 2000);
  setElValue('xAccelStepsInput', s.x_accel_steps || 100);
  setElValue('xScaleInput', s.x_scale || 10);
  setElValue('yMaxSpeedInput', s.y_max_speed || 2000);
  setElValue('yAccelStepsInput', s.y_accel_steps || 100);
  setElValue('yScaleInput', s.y_scale || 10);

  // 馬達鎖定按鈕狀態
  const lockBtn = document.getElementById('btnMotorLock');
  if (lockBtn) lockBtn.className = 'btn-amber-toggle' + (s.motor_locked ? ' on' : '');

  // Arm Down / Vacuum 切換按鈕
  const zBtn = document.getElementById('btnZDown');
  if (zBtn) zBtn.className = `btn-amber-toggle${s.z_down ? ' on' : ''}`;
  const vacBtn = document.getElementById('btnVacuum');
  if (vacBtn) vacBtn.className = `btn-amber-toggle${s.vacuum ? ' on' : ''}`;

  // 監控 Tab - 量規
  drawGauge('gaugeX',  s.x_pulse,  s.x_min,  s.x_max,  '#3b82f6');
  drawGauge('gaugeY1', s.y1_pulse, s.y_min,  s.y_max,  '#10b981');
  drawGauge('gaugeY2', s.y2_pulse, s.y_min,  s.y_max,  '#8b5cf6');
  setEl('gaugeXVal',  el => el.textContent = `${s.x_pulse} µs`);
  setEl('gaugeY1Val', el => el.textContent = `${s.y1_pulse} µs`);
  setEl('gaugeY2Val', el => el.textContent = `${s.y2_pulse} µs`);

  // 監控 Tab - 數位 I/O
  updateTag('mon-vacuum', s.vacuum, '🟢 ON', '⚫ OFF', 'tag-green', 'tag-red');
  updateTag('mon-zdown',  s.z_down, '🟢 ON', '⚫ OFF', 'tag-green', 'tag-red');
  updateTag('mon-limleft',  s.lim_left,  '🔴 觸發', '✔ 正常', 'tag-red', 'tag-green');
  updateTag('mon-limright', s.lim_right, '🔴 觸發', '✔ 正常', 'tag-red', 'tag-green');
  updateTag('mon-limup',    s.lim_up,    '🔴 觸發', '✔ 正常', 'tag-red', 'tag-green');
  updateTag('mon-limdown',  s.lim_down,  '🔴 觸發', '✔ 正常', 'tag-red', 'tag-green');

  // 訊號檢測 Tab
  const duty = (µs) => ((µs / 20000) * 100).toFixed(3);
  setElText('sig-x-pulse', s.x_pulse);
  setElText('sig-y1-pulse', s.y1_pulse);
  setElText('sig-y2-pulse', s.y2_pulse);
  setElText('sig-x-duty',  duty(s.x_pulse));
  setElText('sig-y1-duty', duty(s.y1_pulse));
  setElText('sig-y2-duty', duty(s.y2_pulse));
  setElText('sig-x-pct',  `${xPct.toFixed(1)}%`);
  setElText('sig-y1-pct', `${yPct.toFixed(1)}%`);
  setElText('sig-y2-pct', `${yPct.toFixed(1)}%`);

  // 診斷 Tab
  setElText('diag-x-pulse', s.x_pulse);
  setElText('diag-y1-pulse', s.y1_pulse);
  setElText('diag-y2-pulse', s.y2_pulse);
  setElText('diag-x-duty', duty(s.x_pulse));
  setElText('diag-y1-duty', duty(s.y1_pulse));
  setElText('diag-y2-duty', duty(s.y2_pulse));
  setElText('diag-x-pos',  `${xPct.toFixed(1)}%`);
  setElText('diag-y1-pos', `${yPct.toFixed(1)}%`);
  setElText('diag-y2-pos', `${yPct.toFixed(1)}%`);

  const gpioTag = document.getElementById('diag-gpio-mode');
  if (gpioTag) {
    gpioTag.className = `tag ${s.gpio_mode.includes('Real') ? 'tag-green' : 'tag-amber'}`;
    gpioTag.textContent = s.gpio_mode;
  }

  // 範圍設定顯示
  setElText('curXMin', s.x_min);
  setElText('curXMax', s.x_max);
  setElText('curXRange', `${s.x_max - s.x_min} µs`);
  setElText('curYMin', s.y_min);
  setElText('curYMax', s.y_max);
  setElText('curYRange', `${s.y_max - s.y_min} µs`);

  // GPIO 模式橫幅（診斷頁）
  const modeTitle = document.getElementById('diagModeTitle');
  const modeDesc  = document.getElementById('diagModeDesc');
  if (modeTitle && s.gpio_mode) {
    if (s.gpio_mode.includes('Real')) {
      modeTitle.textContent = '🟢 Raspberry Pi Real GPIO Mode';
      modeTitle.style.color = 'var(--accent-green)';
      if (modeDesc) modeDesc.textContent = '運行在樹梅派硬體上 - 實際 GPIO 輸出已啟用';
    } else {
      modeTitle.textContent = '🟡 Simulation Mode (PC)';
      modeTitle.style.color = 'var(--accent-amber)';
      if (modeDesc) modeDesc.textContent = '非樹梅派環境 - 使用模擬 GPIO，部署到 Pi 後自動切換為實際模式';
    }
  }

  // Chart.js 更新
  if (s.pwm_history && chartX && chartY) {
    chartX.data.datasets[0].data = [...s.pwm_history.x];
    chartX.update('none');
    chartY.data.datasets[0].data = [...s.pwm_history.y1];
    chartY.data.datasets[1].data = [...s.pwm_history.y2];
    chartY.update('none');
  }

  // 位置 tag 更新
  updateMotorTag('tagX',  s.x_pulse,  s.x_min,  s.x_max);
  updateMotorTag('tagY1', s.y1_pulse, s.y_min,  s.y_max);
  updateMotorTag('tagY2', s.y2_pulse, s.y_min,  s.y_max);
}

function updateMotorTag(id, pulse, min, max) {
  const el = document.getElementById(id);
  if (!el) return;
  const pct = (pulse - min) / (max - min) * 100;
  if (pct < 5)       { el.className = 'tag tag-red';    el.textContent = 'MIN'; }
  else if (pct > 95) { el.className = 'tag tag-green';  el.textContent = 'MAX'; }
  else               { el.className = 'tag tag-blue';   el.textContent = 'RUNNING'; }
}

// ── 指示燈 ────────────────────────────────────────────────────
function setLamp(id, mode) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `indicator-lamp ${mode}`;
}

// ── 工具函數 ─────────────────────────────────────────────────
function setEl(id, fn) { const el = document.getElementById(id); if (el) fn(el); }
function setElText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function updateTag(id, active, activeText, inactiveText, activeClass, inactiveClass) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `tag ${active ? activeClass : inactiveClass}`;
  el.textContent = active ? activeText : inactiveText;
}

// ── Tab 切換 ─────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(`tab-content-${name}`)?.classList.add('active');
  document.getElementById(`tab-${name}`)?.classList.add('active');
  if (name === 'diagnose') loadDiagnose();
  if (name === 'simulation3d') {
    init3D();
    if (typeof update3D === 'function') {
      update3D(state);
    }
  }
}

// ── 系統控制 ─────────────────────────────────────────────────
async function cmdStart() {
  const r = await apiPost('/api/start');
  if (r.ok) toast('系統已啟動', 'success');
  addLog('系統啟動', 'success');
}

async function cmdStop() {
  const r = await apiPost('/api/stop');
  if (r.ok) toast('系統已停止', 'info');
  addLog('系統停止', 'warn');
}

async function cmdHome(axis) {
  const r = await apiPost('/api/home', { axis });
  if (r.ok) { toast(`${axis.toUpperCase()} 軸歸零中...`, 'info'); addLog(`歸零: ${axis}`, 'info'); }
}

async function cmdPickup() {
  if (!state.system_run) { toast('請先啟動系統', 'error'); return; }
  const r = await apiPost('/api/pickup');
  if (r.ok) { toast('自動取件流程啟動', 'success'); addLog('自動取件流程啟動', 'success'); }
}

// ── 馬達移動 ─────────────────────────────────────────────────
function moveAxis(axis, dir) {
  if (!state.system_run) { toast('系統未啟動', 'error'); return; }
  const delta = dir * stepSize;
  socket.emit('cmd_move', { axis, delta });
}

function onXSlider(val) {
  if (!state.system_run) return;
  apiPost('/api/set_position', { axis: 'x', pct: parseFloat(val) });
}

function onYSlider(val) {
  if (!state.system_run) return;
  apiPost('/api/set_position', { axis: 'y', pct: parseFloat(val) });
}

// ── 步進值 ───────────────────────────────────────────────────
function setStep(size) {
  stepSize = size;
  document.querySelectorAll('.step-chip').forEach(el => {
    el.classList.toggle('active', parseInt(el.textContent) === size);
  });
}

// ── 數位輸出 ─────────────────────────────────────────────────
async function toggleVacuum() {
  const r = await apiPost('/api/vacuum', { on: !state.vacuum });
  if (r.ok) {
    const status = r.vacuum ? '吸盤 ON' : '吸盤 OFF';
    toast(status, r.vacuum ? 'success' : 'info');
    addLog(status, r.vacuum ? 'success' : 'info');
  }
}

async function toggleZDown() {
  const r = await apiPost('/api/z_down', { on: !state.z_down });
  if (r.ok) {
    const status = r.z_down ? '手臂下降' : '手臂上升';
    toast(status, r.z_down ? 'warn' : 'info');
    addLog(status, r.z_down ? 'warn' : 'info');
  }
}

function setYSync(val) {
  apiPost('/api/set_limits', { y_sync: val });
  document.getElementById('ySyncLabel').textContent = val ? 'ON' : 'OFF';
  document.getElementById('ySyncLabel').style.color = val ? 'var(--accent-green)' : 'var(--accent-red)';
  toast(`Y 軸同步: ${val ? 'ON' : 'OFF'}`, 'info');
}

// ── 範圍設定 ─────────────────────────────────────────────────
async function applyXLimits() {
  const xMin = parseInt(document.getElementById('xMinInput').value);
  const xMax = parseInt(document.getElementById('xMaxInput').value);
  if (xMin >= xMax) { toast('最小值必須小於最大值', 'error'); return; }
  const r = await apiPost('/api/set_limits', { x_min: xMin, x_max: xMax });
  if (r.ok) { toast(`X 軸範圍設定: ${xMin}~${xMax}µs`, 'success'); addLog(`X軸範圍: ${xMin}~${xMax}µs`, 'success'); }
}

async function applyYLimits() {
  const yMin = parseInt(document.getElementById('yMinInput').value);
  const yMax = parseInt(document.getElementById('yMaxInput').value);
  const sync = document.getElementById('ySyncSetting').checked;
  if (yMin >= yMax) { toast('最小值必須小於最大值', 'error'); return; }
  const r = await apiPost('/api/set_limits', { y_min: yMin, y_max: yMax, y_sync: sync });
  if (r.ok) { toast(`Y 軸範圍設定: ${yMin}~${yMax}µs`, 'success'); addLog(`Y軸範圍: ${yMin}~${yMax}µs`, 'success'); }
}

function resetXLimits() {
  document.getElementById('xMinInput').value = 500;
  document.getElementById('xMaxInput').value = 2500;
  document.getElementById('xMinSlider').value = 500;
  document.getElementById('xMaxSlider').value = 2500;
  applyXLimits();
}

function resetYLimits() {
  document.getElementById('yMinInput').value = 500;
  document.getElementById('yMaxInput').value = 2500;
  document.getElementById('yMinSlider').value = 500;
  document.getElementById('yMaxSlider').value = 2500;
  applyYLimits();
}

function clearError() {
  state.error = false;
  state.error_msg = '';
  document.getElementById('errorBanner')?.classList.remove('visible');
}

// ── 診斷 ─────────────────────────────────────────────────────
async function loadDiagnose() {
  try {
    const r = await fetch('/api/diagnose');
    const d = await r.json();
    addDiagLog(`GPIO: ${d.gpio_mode} | PWM: ${d.pwm_freq}Hz`, 'info');
    addDiagLog(`X: ${d.motors?.X?.pulse}µs | Y1: ${d.motors?.Y1?.pulse}µs | Y2: ${d.motors?.Y2?.pulse}µs`, 'info');
    addDiagLog(`VACUUM: ${d.digital_outputs?.VACUUM?.state ? 'ON' : 'OFF'} | Z_DOWN: ${d.digital_outputs?.Z_DOWN?.state ? 'ON' : 'OFF'}`, 'info');
  } catch (e) {
    addDiagLog('診斷資料載入失敗: ' + e.message, 'error');
  }
}

// ── 馬達測試 ─────────────────────────────────────────────────
async function testMotor(axis) {
  if (isTestRunning) return;
  if (!state.system_run) { toast('請先啟動系統', 'error'); return; }
  isTestRunning = true;
  document.getElementById('testStatus').innerHTML = `<span style="color:var(--accent-amber)">⚙️ 正在測試 ${axis.toUpperCase()} 軸...</span>`;
  addDiagLog(`馬達測試開始: ${axis.toUpperCase()} 軸`, 'warn');

  const pulses = [500, 800, 1100, 1500, 1900, 2200, 2500, 1500];
  for (const pulse of pulses) {
    if (!isTestRunning) break;
    await apiPost('/api/set_position', {
      axis: axis,
      pct: (pulse - 500) / 2000 * 100
    });
    addDiagLog(`${axis.toUpperCase()}: ${pulse}µs`, 'info');
    await sleep(600);
  }

  isTestRunning = false;
  document.getElementById('testStatus').innerHTML = `<span style="color:var(--accent-green)">✅ ${axis.toUpperCase()} 軸測試完成</span>`;
  addDiagLog(`馬達測試完成: ${axis.toUpperCase()} 軸`, 'success');
}

async function testVacuum() {
  if (!state.system_run) { toast('請先啟動系統', 'error'); return; }
  addDiagLog('吸盤測試: ON', 'warn');
  await apiPost('/api/vacuum', { on: true });
  await sleep(1000);
  await apiPost('/api/vacuum', { on: false });
  addDiagLog('吸盤測試: OFF', 'info');
  document.getElementById('testStatus').innerHTML = `<span style="color:var(--accent-green)">✅ VACUUM 測試完成</span>`;
}

function stopTest() {
  isTestRunning = false;
  if (testInterval) { clearInterval(testInterval); testInterval = null; }
  document.getElementById('testStatus').innerHTML = `<span style="color:var(--accent-red)">⏹ 測試已停止</span>`;
  addDiagLog('測試停止', 'warn');
}

// ── 日誌 ─────────────────────────────────────────────────────
function addLog(msg, type = 'info') {
  const panel = document.getElementById('logPanel');
  if (!panel) return;
  const time = new Date().toLocaleTimeString('zh-TW', { hour12: false });
  const colors = { info: 'var(--accent-cyan)', warn: 'var(--accent-amber)', error: 'var(--accent-red)', success: 'var(--accent-green)' };
  const icons  = { info: 'ℹ', warn: '⚠', error: '✘', success: '✔' };
  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `<span class="log-time">[${time}]</span> <span style="color:${colors[type] || 'var(--text-sec)'}">${icons[type] || '·'} ${msg}</span>`;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
  if (panel.children.length > 200) panel.removeChild(panel.firstChild);
}

function addDiagLog(msg, type = 'info') {
  const panel = document.getElementById('diagLog');
  if (!panel) return;
  const time = new Date().toLocaleTimeString('zh-TW', { hour12: false });
  const colors = { info: 'var(--accent-cyan)', warn: 'var(--accent-amber)', error: 'var(--accent-red)', success: 'var(--accent-green)' };
  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `<span class="log-time">[${time}]</span> <span style="color:${colors[type] || 'var(--text-sec)'}">${msg}</span>`;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}

function clearLog() {
  const panel = document.getElementById('logPanel');
  if (panel) panel.innerHTML = '';
}

// ── Toast 通知 ───────────────────────────────────────────────
function toast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const t = document.createElement('div');
  const icons = { success: '✔', error: '✘', info: 'ℹ', warn: '⚠' };
  t.className = `toast toast-${type === 'warn' ? 'info' : type}`;
  t.innerHTML = `<span>${icons[type] || 'ℹ'}</span>${msg}`;
  container.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ── API 工具 ─────────────────────────────────────────────────
async function apiPost(url, body = {}) {
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return await r.json();
  } catch (e) {
    addLog(`API 錯誤: ${url} - ${e.message}`, 'error');
    return { ok: false, msg: e.message };
  }
}

function setElValue(id, val) {
  const el = document.getElementById(id);
  if (el && document.activeElement !== el) el.value = val;
}

// ── 進階設定套用 ────────────────────────────────────────────────
async function applyAdvancedLimits() {
  const xMaxSpeed = parseFloat(document.getElementById('xMaxSpeedInput').value);
  const xAccelSteps = parseFloat(document.getElementById('xAccelStepsInput').value);
  const xScale = parseFloat(document.getElementById('xScaleInput').value);
  const yMaxSpeed = parseFloat(document.getElementById('yMaxSpeedInput').value);
  const yAccelSteps = parseFloat(document.getElementById('yAccelStepsInput').value);
  const yScale = parseFloat(document.getElementById('yScaleInput').value);
  
  const r = await apiPost('/api/set_limits', {
    x_max_speed: xMaxSpeed, x_accel_steps: xAccelSteps, x_scale: xScale,
    y_max_speed: yMaxSpeed, y_accel_steps: yAccelSteps, y_scale: yScale
  });
  if (r.ok) {
    toast('進階加減速與校準參數已套用！', 'success');
  }
}

// ── 馬達鎖定/致能開關 ───────────────────────────────────────────
async function toggleMotorLock() {
  const r = await apiPost('/api/set_motor_enable', { locked: !state.motor_locked });
  if (r.ok) {
    toast(r.motor_locked ? '馬達已通電鎖定' : '馬達已斷電釋放 (可手動推動)', r.motor_locked ? 'success' : 'warn');
  }
}

// ── 操作歷史紀錄 ───────────────────────────────────────────────
let historyList = [];

socket.on('new_history', (log) => {
  historyList.push(log);
  if (historyList.length > 200) historyList.shift();
  renderHistory();
});

async function loadHistory() {
  try {
    const r = await fetch('/api/history');
    const data = await r.json();
    if (data.ok) {
      historyList = data.history;
      renderHistory();
    }
  } catch (e) {
    console.error("載入歷史失敗: ", e);
  }
}

function renderHistory(filterText = "") {
  const tbody = document.getElementById('historyTableBody');
  if (!tbody) return;
  tbody.innerHTML = "";
  
  const typeColors = {
    success: 'var(--accent-green)',
    warn: 'var(--accent-amber)',
    error: 'var(--accent-red)',
    info: 'var(--accent-cyan)'
  };
  
  const filtered = historyList.filter(item => 
    item.msg.toLowerCase().includes(filterText.toLowerCase()) ||
    item.type.toLowerCase().includes(filterText.toLowerCase())
  );
  
  [...filtered].reverse().forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-family:'JetBrains Mono';font-size:11px;color:var(--text-dim)">${item.time}</td>
      <td><span class="tag" style="background:${typeColors[item.type] || 'gray'};color:#000;font-weight:bold;padding:2px 6px;border-radius:4px;font-size:10px">${item.type.toUpperCase()}</span></td>
      <td style="color:var(--text-main);font-size:12px">${item.msg}</td>
    `;
    tbody.appendChild(tr);
  });
}

function filterHistory() {
  const text = document.getElementById('historySearch').value;
  renderHistory(text);
}

async function clearHistory() {
  if (confirm("確定要清空所有歷史紀錄嗎？")) {
    const res = await fetch('/api/history', { method: 'DELETE' });
    const d = await res.json();
    if (d.ok) {
      historyList = [];
      renderHistory();
      toast('歷史紀錄已清除', 'info');
    }
  }
}

// ── 動作巨集編輯與控制 ───────────────────────────────────────────
let macros = {};
let currentMacroName = "";

async function loadMacros() {
  try {
    const r = await fetch('/api/macros');
    const data = await r.json();
    if (data.ok) {
      macros = data.macros;
      populateMacroList();
    }
  } catch (e) {
    console.error("載入巨集失敗: ", e);
  }
}

function populateMacroList() {
  const sel = document.getElementById('macroSelect');
  if (!sel) return;
  const prevVal = sel.value;
  sel.innerHTML = "";
  
  Object.keys(macros).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
  
  if (prevVal && macros[prevVal]) {
    sel.value = prevVal;
  } else if (sel.options.length > 0) {
    sel.value = sel.options[0].value;
  }
  onMacroSelect(sel.value);
}

function onMacroSelect(name) {
  currentMacroName = name;
  const editor = document.getElementById('macroEditor');
  if (editor && macros[name]) {
    editor.value = macros[name].join('\n');
  }
}

async function saveCurrentMacro() {
  if (!currentMacroName) {
    toast("請先選擇或新增一個巨集", "error");
    return;
  }
  const text = document.getElementById('macroEditor').value;
  const commands = text.split('\n');
  const r = await apiPost('/api/macros', { name: currentMacroName, commands });
  if (r.ok) {
    macros[currentMacroName] = commands;
    toast(`巨集「${currentMacroName}」儲存成功！`, "success");
  }
}

async function createMacro() {
  const name = document.getElementById('newMacroName').value.trim();
  if (!name) {
    toast("請輸入巨集名稱", "error");
    return;
  }
  if (macros[name]) {
    toast("巨集名稱已存在", "error");
    return;
  }
  const commands = ["# 新巨集腳本", "HOME", "DELAY 500"];
  const r = await apiPost('/api/macros', { name, commands });
  if (r.ok) {
    macros[name] = commands;
    populateMacroList();
    document.getElementById('macroSelect').value = name;
    onMacroSelect(name);
    document.getElementById('newMacroName').value = "";
    toast(`巨集「${name}」新增成功`, "success");
  }
}

async function deleteMacro() {
  if (!currentMacroName) return;
  if (confirm(`確定要刪除巨集「${currentMacroName}」嗎？`)) {
    const r = await fetch('/api/macros', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: currentMacroName })
    });
    const data = await r.json();
    if (data.ok) {
      delete macros[currentMacroName];
      currentMacroName = "";
      populateMacroList();
      toast("巨集已刪除", "info");
    }
  }
}

async function runMacro() {
  if (!currentMacroName) return;
  const r = await apiPost('/api/macro/run', { action: 'start', name: currentMacroName });
  if (r.ok) {
    toast("巨集已啟動執行...", "success");
  } else {
    toast(r.msg, "error");
  }
}

async function pauseMacro() {
  const btn = document.getElementById('btnPauseMacro');
  const action = btn.textContent.includes("暫停") ? "pause" : "resume";
  const r = await apiPost('/api/macro/run', { action });
  if (r.ok) {
    if (action === "pause") {
      btn.textContent = "▶ 繼續";
      btn.className = "btn btn-success";
    } else {
      btn.textContent = "⏸ 暫停";
      btn.className = "btn btn-amber";
    }
  }
}

async function stopMacro() {
  const r = await apiPost('/api/macro/run', { action: 'stop' });
  if (r.ok) {
    toast("已發送停止指令", "warn");
  }
}

socket.on('macro_status', (data) => {
  const statusText = document.getElementById('macroStatusText');
  const lineText = document.getElementById('macroCurrentLine');
  
  const runBtn = document.getElementById('btnRunMacro');
  const pauseBtn = document.getElementById('btnPauseMacro');
  const stopBtn = document.getElementById('btnStopMacro');
  
  if (statusText) {
    if (data.running) {
      statusText.textContent = data.paused ? "PAUSED" : "RUNNING";
      statusText.style.color = data.paused ? "var(--accent-amber)" : "var(--accent-green)";
    } else {
      statusText.textContent = "IDLE";
      statusText.style.color = "var(--accent-cyan)";
    }
  }
  
  if (lineText && data.current_line !== undefined) {
    lineText.textContent = data.current_line;
  }
  
  if (runBtn) runBtn.disabled = data.running;
  if (pauseBtn) {
    pauseBtn.disabled = !data.running;
    if (!data.running) {
      pauseBtn.textContent = "⏸ 暫停";
      pauseBtn.className = "btn btn-amber";
    } else if (data.paused) {
      pauseBtn.textContent = "▶ 繼續";
      pauseBtn.className = "btn btn-success";
    } else {
      pauseBtn.textContent = "⏸ 暫停";
      pauseBtn.className = "btn btn-amber";
    }
  }
  if (stopBtn) stopBtn.disabled = !data.running;
});

socket.on('macro_msg', (data) => {
  toast(`[巨集提示] ${data.msg}`, 'success');
});

// ── G-code 解析與圖形繪製 ────────────────────────────────────────
let gcodeLines = [];
let gcodeRunning = false;
let gcodeIndex = 0;

function loadGcodeFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  document.getElementById('gcodeFileName').textContent = file.name;
  
  const reader = new FileReader();
  reader.onload = function(e) {
    const text = e.target.result;
    gcodeLines = text.split('\n');
    document.getElementById('gcodeTotalLines').textContent = gcodeLines.length;
    document.getElementById('gcodeProgress').textContent = `0 / ${gcodeLines.length}`;
    document.getElementById('btnRunGcode').disabled = false;
    
    drawGcodePath();
  };
  reader.readAsText(file);
}

function drawGcodePath() {
  const canvas = document.getElementById('gcodeCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  // 繪製格線
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 50; i < 300; i += 50) {
    ctx.moveTo(i, 0); ctx.lineTo(i, 300);
    ctx.moveTo(0, i); ctx.lineTo(300, i);
  }
  ctx.stroke();
  
  // 繪製軌跡
  ctx.strokeStyle = '#3b82f6';
  ctx.lineWidth = 2;
  ctx.beginPath();
  
  let lastX = 0, lastY = 0;
  let first = true;
  
  gcodeLines.forEach(line => {
    line = line.split(';')[0].split('(')[0].trim();
    if (!line) return;
    const parts = line.split(/\s+/);
    const cmd = parts[0].toUpperCase();
    
    if (cmd === 'G0' || cmd === 'G1') {
      let newX = lastX, newY = lastY;
      parts.forEach(part => {
        if (part.startsWith('X') || part.startsWith('x')) {
          newX = parseFloat(part.substring(1));
        } else if (part.startsWith('Y') || part.startsWith('y')) {
          newY = parseFloat(part.substring(1));
        }
      });
      
      const canvasX = (newX / 200.0) * 300;
      const canvasY = 300 - (newY / 200.0) * 300;
      
      if (first) {
        ctx.moveTo(canvasX, canvasY);
        first = false;
      } else {
        ctx.lineTo(canvasX, canvasY);
      }
      
      lastX = newX;
      lastY = newY;
    }
  });
  ctx.stroke();
  
  // 繪製起點紅點
  ctx.fillStyle = '#ef4444';
  ctx.beginPath();
  ctx.arc(0, 300, 5, 0, Math.PI * 2);
  ctx.fill();
}

async function runGcode() {
  if (gcodeLines.length === 0 || gcodeRunning) return;
  
  gcodeRunning = true;
  document.getElementById('btnRunGcode').disabled = true;
  document.getElementById('btnStopGcode').disabled = false;
  
  addLog("G-code 執行開始", "success");
  
  let lastX = 0, lastY = 0;
  
  for (gcodeIndex = 0; gcodeIndex < gcodeLines.length; gcodeIndex++) {
    if (!gcodeRunning) break;
    
    document.getElementById('gcodeProgress').textContent = `${gcodeIndex + 1} / ${gcodeLines.length}`;
    
    let line = gcodeLines[gcodeIndex].split(';')[0].split('(')[0].trim();
    if (!line) continue;
    
    const parts = line.split(/\s+/);
    const cmd = parts[0].toUpperCase();
    
    if (cmd === 'G0' || cmd === 'G1') {
      let targetX = lastX;
      let targetY = lastY;
      let hasMove = false;
      
      parts.forEach(part => {
        if (part.startsWith('X') || part.startsWith('x')) {
          targetX = parseFloat(part.substring(1));
          hasMove = true;
        } else if (part.startsWith('Y') || part.startsWith('y')) {
          targetY = parseFloat(part.substring(1));
          hasMove = true;
        }
      });
      
      if (hasMove) {
        const xScale = state.x_scale || 10.0;
        const yScale = state.y_scale || 10.0;
        const pulseX = 500 + targetX * xScale;
        const pulseY = 500 + targetY * yScale;
        
        await apiPost('/api/set_position', { axis: 'x', pct: (pulseX - state.x_min) / (state.x_max - state.x_min) * 100 });
        await apiPost('/api/set_position', { axis: 'y', pct: (pulseY - state.y_min) / (state.y_max - state.y_min) * 100 });
        
        while (gcodeRunning) {
          const diffX = Math.abs(state.x_pulse - pulseX);
          const diffY = Math.abs(state.y1_pulse - pulseY);
          if (diffX < 10 && diffY < 10) {
            break;
          }
          await sleep(100);
        }
        
        lastX = targetX;
        lastY = targetY;
      }
    } else if (cmd === 'G28') {
      await apiPost('/api/home', { axis: 'all' });
      await sleep(2000);
      lastX = 0;
      lastY = 0;
    } else if (cmd === 'M106') {
      await apiPost('/api/vacuum', { on: true });
      await sleep(500);
    } else if (cmd === 'M107') {
      await apiPost('/api/vacuum', { on: false });
      await sleep(500);
    }
  }
  
  gcodeRunning = false;
  document.getElementById('btnRunGcode').disabled = false;
  document.getElementById('btnStopGcode').disabled = true;
  addLog("G-code 執行結束", "success");
  toast("G-code 執行完成！", "success");
}

function stopGcode() {
  gcodeRunning = false;
  document.getElementById('btnRunGcode').disabled = false;
  document.getElementById('btnStopGcode').disabled = true;
  addLog("G-code 執行已被使用者終止", "warn");
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── 時鐘 ─────────────────────────────────────────────────────
function updateClock() {
  const el = document.getElementById('clockDisplay');
  if (el) el.textContent = new Date().toLocaleTimeString('zh-TW', { hour12: false });
}

// ── 鍵盤快捷鍵 ───────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (!state.system_run) return;
  switch (e.key) {
    case 'ArrowLeft':  e.preventDefault(); moveAxis('x', -1); break;
    case 'ArrowRight': e.preventDefault(); moveAxis('x',  1); break;
    case 'ArrowUp':    e.preventDefault(); moveAxis('y',  1); break;
    case 'ArrowDown':  e.preventDefault(); moveAxis('y', -1); break;
    case 'v': case 'V': toggleVacuum(); break;
    case 'z': case 'Z': toggleZDown(); break;
    case 'h': case 'H': cmdHome('all'); break;
  }
});

// ── 初始化 ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initCharts();
  setInterval(updateClock, 1000);
  updateClock();
  loadHistory();
  loadMacros();
  addLog('系統介面載入完成', 'success');
  addLog('使用 ← → ↑ ↓ 方向鍵快速控制馬達', 'info');
  addLog('V=吸盤切換 | Z=手臂切換 | H=全部歸零', 'info');
});
