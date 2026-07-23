const API = '';

function authHeaders() {
  return { 'Content-Type': 'application/json' };
}

// ---- DOM 引用 ----
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const app = $('#app');
const loginView = $('#loginView');
const loginForm = $('#loginForm');
const usernameInput = $('#usernameInput');
const passwordInput = $('#passwordInput');
const loginError = $('#loginError');
const currentUser = $('#currentUser');
const logoutBtn = $('#logoutBtn');

const nlInput = $('#nlInput');
const translateBtn = $('#translateBtn');
const promptInput = $('#promptInput');
const negInput = $('#negInput');
const negDetail = $('#negDetail');

const widthSlider = $('#widthSlider');
const widthInput = $('#widthInput');
const heightSlider = $('#heightSlider');
const heightInput = $('#heightInput');
const wVal = $('#wVal');
const hVal = $('#hVal');
const swapBtn = $('#swapBtn');
const resSummary = $('#resSummary');

const stepsInput = $('#steps');
const cfgInput = $('#cfg');
const seedInput = $('#seed');
const samplerInput = $('#sampler');
const advSummary = $('#advSummary');

const generateBtn = $('#generateBtn');
const cancelBtn = $('#cancelBtn');
const statusBar = $('#statusBar');

const resultSection = $('#resultSection');
const resultImg = $('#resultImg');
const resultInfo = $('#resultInfo');

const historyList = $('#historyList');

// ---- 分辨率同步 ----
const RES_PRESETS = [
  [576, 1024, '9:16'],
  [768, 1024, '3:4'],
  [1024, 1024, '1:1'],
  [1024, 768, '4:3'],
  [1024, 576, '16:9'],
];

let updatingRes = false;

function setWidth(v) {
  widthSlider.value = widthInput.value = v;
  wVal.textContent = v;
  updateResSummary();
  highlightPreset();
}

function setHeight(v) {
  heightSlider.value = heightInput.value = v;
  hVal.textContent = v;
  updateResSummary();
  highlightPreset();
}

function updateResSummary() {
  const w = +widthInput.value, h = +heightInput.value;
  let label = `${w} × ${h}`;
  if (w > h) label += ' (横屏)';
  else if (h > w) label += ' (竖屏)';
  else label += ' (正方形)';
  resSummary.textContent = `分辨率: ${label}`;
}

function highlightPreset() {
  const w = +widthInput.value, h = +heightInput.value;
  $$('.preset').forEach(b => {
    b.classList.toggle('active', +b.dataset.w === w && +b.dataset.h === h);
  });
}

widthSlider.addEventListener('input', () => setWidth(widthSlider.value));
widthInput.addEventListener('change', () => {
  let v = +widthInput.value;
  v = Math.round(v / 8) * 8;
  v = Math.max(256, Math.min(1536, v));
  setWidth(v);
});
heightSlider.addEventListener('input', () => setHeight(heightSlider.value));
heightInput.addEventListener('change', () => {
  let v = +heightInput.value;
  v = Math.round(v / 8) * 8;
  v = Math.max(256, Math.min(1536, v));
  setHeight(v);
});

swapBtn.addEventListener('click', () => {
  const w = +widthInput.value, h = +heightInput.value;
  setWidth(h);
  setHeight(w);
});

$$('.preset').forEach(b => {
  b.addEventListener('click', () => {
    setWidth(+b.dataset.w);
    setHeight(+b.dataset.h);
  });
});

// ---- 高级参数 summary 更新 ----
function updateAdvSummary() {
  advSummary.textContent = `高级参数: steps ${stepsInput.value} / CFG ${cfgInput.value} / ${samplerInput.value}`;
}
[stepsInput, cfgInput, samplerInput].forEach(el => el.addEventListener('input', updateAdvSummary));

// ---- 翻译 ----
translateBtn.addEventListener('click', async () => {
  const text = nlInput.value.trim();
  if (!text) return;

  translateBtn.textContent = '增强中...';
  translateBtn.classList.add('loading');

  try {
    const resp = await fetch(`${API}/api/enhance-prompt`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '增强失败');
    }
    const data = await resp.json();
    promptInput.value = data.prompt;
    negInput.value = data.negative_prompt;
    if (data.negative_prompt) negDetail.open = true;
  } catch (e) {
    alert(`AI 增强失败: ${e.message}`);
  } finally {
    translateBtn.textContent = 'AI 增强';
    translateBtn.classList.remove('loading');
  }
});

// ---- 生成 ----
let generating = false;
let currentTaskId = null;

generateBtn.addEventListener('click', async () => {
  if (generating) return;
  const prompt = promptInput.value.trim();
  if (!prompt) { alert('请输入提示词'); return; }

  generating = true;
  generateBtn.disabled = true;
  generateBtn.textContent = '排队中...';
  statusBar.classList.remove('hidden');
  statusBar.classList.add('running');
  statusBar.textContent = '提交任务...';

  try {
    const params = {
      prompt,
      negative_prompt: negInput.value,
      width: +widthInput.value,
      height: +heightInput.value,
      steps: +stepsInput.value,
      cfg_scale: +cfgInput.value,
      sampler_name: samplerInput.value,
      seed: +seedInput.value,
    };

    // 1. 提交任务
    let resp = await fetch(`${API}/api/generate`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '提交失败');
    }
    const { task_id } = await resp.json();
    currentTaskId = task_id;
    cancelBtn.classList.remove('hidden');
    statusBar.textContent = '排队中...';

    // 2. 长轮询等待完成
    resp = await fetch(`${API}/api/task/${task_id}/wait`, {
      headers: authHeaders(),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '生成失败');
    }
    const data = await resp.json();

    // 3. 显示结果
    resultSection.style.display = '';
    resultImg.src = data.image_url;
    resultInfo.textContent = JSON.stringify(data.params, null, 2);
    statusBar.classList.add('hidden');

    // 4. 刷新历史
    loadHistory();

  } catch (e) {
    statusBar.textContent = `错误: ${e.message}`;
    statusBar.classList.remove('running');
  } finally {
    generating = false;
    currentTaskId = null;
    cancelBtn.classList.add('hidden');
    generateBtn.disabled = false;
    generateBtn.textContent = '生成';
  }
});

cancelBtn.addEventListener('click', async () => {
  if (!currentTaskId) return;
  cancelBtn.disabled = true;
  try {
    const resp = await fetch(`${API}/api/cancel`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ task_id: currentTaskId }),
    });
    const data = await resp.json();
    statusBar.textContent = data.cancelled ? '正在取消...' : '任务已经结束';
  } finally {
    cancelBtn.disabled = false;
  }
});

// ---- 历史记录 ----
async function loadHistory() {
  try {
    const resp = await fetch(`${API}/api/history?limit=30`, { headers: authHeaders() });
    const items = await resp.json();
    historyList.replaceChildren();
    items.forEach(item => {
      const el = document.createElement('div');
      el.className = 'history-item';
      el.dataset.url = item.image_url;
      el.dataset.params = JSON.stringify(item.params);
      const img = document.createElement('img');
      img.src = item.image_url;
      img.loading = 'lazy';
      img.alt = '历史生成图片';
      el.appendChild(img);
      historyList.appendChild(el);
    });

    // 点击历史项 → 放大查看
    $$('.history-item').forEach(el => {
      el.addEventListener('click', () => {
        resultSection.style.display = '';
        resultImg.src = el.dataset.url;
        try {
          resultInfo.textContent = JSON.stringify(JSON.parse(el.dataset.params), null, 2);
        } catch (_) { resultInfo.textContent = ''; }
        // 滚动到图片
        resultImg.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // 恢复提示词输入（方便复用参数）
        try {
          const p = JSON.parse(el.dataset.params);
          if (p.prompt) promptInput.value = p.prompt;
          if (p.negative_prompt) negInput.value = p.negative_prompt;
        } catch (_) {}
      });
    });
  } catch (e) {
    console.error('加载历史失败:', e);
  }
}

function showLogin() {
  app.classList.add('hidden');
  loginView.classList.remove('hidden');
}

function showApp(username) {
  currentUser.textContent = username;
  loginView.classList.add('hidden');
  app.classList.remove('hidden');
  loadHistory();
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginError.textContent = '';
  const resp = await fetch(`${API}/api/login`, {
    method: 'POST', headers: authHeaders(),
    body: JSON.stringify({ username: usernameInput.value.trim(), password: passwordInput.value }),
  });
  if (!resp.ok) {
    const error = await resp.json().catch(() => ({}));
    loginError.textContent = error.detail || '登录失败';
    return;
  }
  const data = await resp.json();
  passwordInput.value = '';
  showApp(data.username);
});

logoutBtn.addEventListener('click', async () => {
  await fetch(`${API}/api/logout`, { method: 'POST', headers: authHeaders() });
  historyList.replaceChildren();
  showLogin();
});

async function initialize() {
  highlightPreset();
  updateResSummary();
  updateAdvSummary();
  const resp = await fetch(`${API}/api/me`, { headers: authHeaders() });
  if (resp.ok) showApp((await resp.json()).username);
  else showLogin();
}

initialize();
