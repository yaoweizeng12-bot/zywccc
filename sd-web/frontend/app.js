const API = '';
const MAX_PIXELS = 1572864;
const MIN_SIDE = 256;
const MAX_SIDE = 1536;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
const authHeaders = () => ({ 'Content-Type': 'application/json' });

const app = $('#app');
const loginView = $('#loginView');
const loginForm = $('#loginForm');
const usernameInput = $('#usernameInput');
const passwordInput = $('#passwordInput');
const loginError = $('#loginError');
const currentUser = $('#currentUser');
const logoutBtn = $('#logoutBtn');
const actionDock = $('#actionDock');

const nlInput = $('#nlInput');
const clearBtn = $('#clearBtn');
const translateBtn = $('#translateBtn');
const promptDetail = $('#promptDetail');
const promptInput = $('#promptInput');
const negInput = $('#negInput');
const negDetail = $('#negDetail');

const widthInput = $('#widthInput');
const heightInput = $('#heightInput');
const swapBtn = $('#swapBtn');
const customToggle = $('#customToggle');
const customSize = $('#customSize');
const applySizeBtn = $('#applySizeBtn');
const resSummary = $('#resSummary');
const pixelMeter = $('#pixelMeter');
const sizeStatus = $('#sizeStatus');

const stepsInput = $('#steps');
const cfgInput = $('#cfg');
const seedInput = $('#seed');
const samplerInput = $('#sampler');
const advSummary = $('#advSummary');

const generateBtn = $('#generateBtn');
const cancelBtn = $('#cancelBtn');
const randomIdeaBtn = $('#randomIdeaBtn');
const statusBar = $('#statusBar');
const resultSection = $('#resultSection');
const resultImg = $('#resultImg');
const resultInfo = $('#resultInfo');
const historyList = $('#historyList');

const downloadBtn = $('#downloadBtn');
const copyPromptBtn = $('#copyPromptBtn');
const rerollBtn = $('#rerollBtn');
const shareBtn = $('#shareBtn');
const toast = $('#toast');
const imageModal = $('#imageModal');
const modalImg = $('#modalImg');
const closeModalBtn = $('#closeModalBtn');

let generating = false;
let currentTaskId = null;
let toastTimer = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
}

async function readError(resp, fallback) {
  const data = await resp.json().catch(() => ({}));
  if (resp.status === 401) showLogin();
  return data.detail || fallback;
}

function normalizeSide(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return MIN_SIDE;
  return Math.max(MIN_SIDE, Math.min(MAX_SIDE, Math.round(number / 8) * 8));
}

function validateResolution() {
  const width = Number(widthInput.value);
  const height = Number(heightInput.value);
  const pixels = width * height;
  const sidesValid = Number.isInteger(width) && Number.isInteger(height)
    && width >= MIN_SIDE && height >= MIN_SIDE
    && width <= MAX_SIDE && height <= MAX_SIDE
    && width % 8 === 0 && height % 8 === 0;
  const valid = sidesValid && pixels <= MAX_PIXELS;

  resSummary.textContent = `${width || 0} × ${height || 0} · ${(pixels / 1e6 || 0).toFixed(2)}MP`;
  pixelMeter.classList.toggle('invalid', !valid);
  sizeStatus.textContent = valid ? '可生成' : pixels > MAX_PIXELS ? '超过 1.57MP' : '尺寸无效';
  generateBtn.disabled = generating || !valid;
  highlightPreset();
  return valid;
}

function applyResolution(width, height) {
  widthInput.value = normalizeSide(width);
  heightInput.value = normalizeSide(height);
  return validateResolution();
}

function highlightPreset() {
  const width = Number(widthInput.value);
  const height = Number(heightInput.value);
  $$('.preset').forEach((button) => {
    button.classList.toggle('active', Number(button.dataset.w) === width && Number(button.dataset.h) === height);
  });
}

$$('.preset').forEach((button) => {
  button.addEventListener('click', () => applyResolution(button.dataset.w, button.dataset.h));
});

customToggle.addEventListener('click', () => {
  customSize.classList.toggle('show');
  customToggle.textContent = customSize.classList.contains('show') ? '收起' : '自定义';
});

applySizeBtn.addEventListener('click', () => {
  const valid = applyResolution(widthInput.value, heightInput.value);
  showToast(valid ? `已应用 ${widthInput.value} × ${heightInput.value}` : '总像素超过限制');
});

[widthInput, heightInput].forEach((input) => input.addEventListener('input', validateResolution));
swapBtn.addEventListener('click', () => {
  const width = widthInput.value;
  applyResolution(heightInput.value, width);
});

function updateAdvSummary() {
  advSummary.textContent = `${stepsInput.value} Steps · CFG ${cfgInput.value}　⌄`;
}
[stepsInput, cfgInput, samplerInput].forEach((input) => input.addEventListener('input', updateAdvSummary));

clearBtn.addEventListener('click', () => {
  nlInput.value = '';
  nlInput.focus();
});

translateBtn.addEventListener('click', async () => {
  const text = nlInput.value.trim();
  if (!text) {
    showToast('先描述一下想画的画面');
    nlInput.focus();
    return;
  }

  translateBtn.classList.add('loading');
  translateBtn.querySelector('span').textContent = '正在优化…';
  try {
    const resp = await fetch(`${API}/api/enhance-prompt`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ text }),
    });
    if (!resp.ok) throw new Error(await readError(resp, '增强失败'));
    const data = await resp.json();
    promptInput.value = data.prompt;
    negInput.value = data.negative_prompt;
    promptDetail.open = true;
    if (data.negative_prompt) negDetail.open = true;
    showToast('提示词已优化');
  } catch (error) {
    showToast(`AI 增强失败：${error.message}`);
  } finally {
    translateBtn.classList.remove('loading');
    translateBtn.querySelector('span').textContent = 'AI 优化提示词';
  }
});

function currentParams() {
  return {
    prompt: promptInput.value.trim(),
    negative_prompt: negInput.value,
    width: Number(widthInput.value),
    height: Number(heightInput.value),
    steps: Number(stepsInput.value),
    cfg_scale: Number(cfgInput.value),
    sampler_name: samplerInput.value,
    seed: Number(seedInput.value),
  };
}

async function generate() {
  if (generating || !validateResolution()) return;
  const params = currentParams();
  if (!params.prompt) {
    promptDetail.open = true;
    showToast('请先填写或生成英文提示词');
    promptInput.focus();
    return;
  }

  document.activeElement?.blur();
  generating = true;
  generateBtn.disabled = true;
  generateBtn.textContent = '正在提交…';
  statusBar.classList.remove('hidden');
  statusBar.classList.add('running');
  statusBar.textContent = '正在提交任务…';

  try {
    let resp = await fetch(`${API}/api/generate`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(params),
    });
    if (!resp.ok) throw new Error(await readError(resp, '提交失败'));
    const submitted = await resp.json();
    currentTaskId = submitted.task_id;
    cancelBtn.classList.remove('hidden');
    generateBtn.textContent = submitted.queue_position > 1 ? `排队中 · 第 ${submitted.queue_position} 位` : '正在生成…';
    statusBar.textContent = submitted.queue_position > 1 ? `任务已提交，当前排队第 ${submitted.queue_position} 位` : 'GPU 正在生成图片…';

    resp = await fetch(`${API}/api/task/${currentTaskId}/wait`, { headers: authHeaders() });
    if (!resp.ok) throw new Error(await readError(resp, '生成失败'));
    const data = await resp.json();
    showResult(data.image_url, data.params);
    statusBar.classList.add('hidden');
    showToast('图片生成完成');
    await loadHistory();
  } catch (error) {
    statusBar.textContent = `生成失败：${error.message}`;
    statusBar.classList.remove('running');
  } finally {
    generating = false;
    currentTaskId = null;
    cancelBtn.classList.add('hidden');
    generateBtn.textContent = '生成图片';
    validateResolution();
  }
}

generateBtn.addEventListener('click', generate);
rerollBtn.addEventListener('click', generate);

cancelBtn.addEventListener('click', async () => {
  if (!currentTaskId) return;
  cancelBtn.disabled = true;
  try {
    const resp = await fetch(`${API}/api/cancel`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ task_id: currentTaskId }),
    });
    const data = await resp.json().catch(() => ({}));
    statusBar.textContent = data.cancelled ? '正在取消任务…' : '任务已经结束';
  } finally {
    cancelBtn.disabled = false;
  }
});

function showResult(url, params = {}) {
  resultSection.hidden = false;
  resultImg.src = url;
  resultInfo.textContent = JSON.stringify(params, null, 2);
}

async function loadHistory() {
  try {
    const resp = await fetch(`${API}/api/history?limit=30`, { headers: authHeaders() });
    if (!resp.ok) throw new Error(await readError(resp, '加载历史失败'));
    const items = await resp.json();
    historyList.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-history';
      empty.textContent = '还没有作品，生成第一张吧';
      historyList.appendChild(empty);
      return;
    }

    items.forEach((item) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'history-item';
      const img = document.createElement('img');
      img.src = item.thumbnail_url || item.image_url;
      img.loading = 'lazy';
      img.alt = '历史生成图片';
      const meta = document.createElement('span');
      meta.className = 'history-meta';
      const width = item.params?.width || '?';
      const height = item.params?.height || '?';
      meta.textContent = `${width} × ${height} · Seed ${item.params?.seed ?? '?'}`;
      button.append(img, meta);
      button.addEventListener('click', () => restoreHistory(item));
      historyList.appendChild(button);
    });
  } catch (error) {
    console.error(error);
  }
}

function restoreHistory(item) {
  const params = item.params || {};
  showResult(item.image_url, params);
  if (params.prompt) promptInput.value = params.prompt;
  if (params.negative_prompt) negInput.value = params.negative_prompt;
  if (params.width && params.height) applyResolution(params.width, params.height);
  if (params.steps) stepsInput.value = params.steps;
  if (params.cfg_scale) cfgInput.value = params.cfg_scale;
  if (params.sampler_name) samplerInput.value = params.sampler_name;
  if (Number.isInteger(params.seed)) seedInput.value = params.seed;
  updateAdvSummary();
  resultSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

resultImg.addEventListener('click', () => {
  modalImg.src = resultImg.src;
  imageModal.classList.add('show');
});
closeModalBtn.addEventListener('click', () => imageModal.classList.remove('show'));
imageModal.addEventListener('click', (event) => {
  if (event.target === imageModal) imageModal.classList.remove('show');
});

downloadBtn.addEventListener('click', () => {
  if (!resultImg.src) return;
  const link = document.createElement('a');
  link.href = resultImg.src;
  link.download = `sd-${Date.now()}.png`;
  document.body.appendChild(link);
  link.click();
  link.remove();
});

copyPromptBtn.addEventListener('click', async () => {
  if (!promptInput.value) return showToast('当前没有提示词');
  await navigator.clipboard.writeText(promptInput.value);
  showToast('提示词已复制');
});

shareBtn.addEventListener('click', async () => {
  if (!resultImg.src) return;
  try {
    const blob = await (await fetch(resultImg.src)).blob();
    const file = new File([blob], 'sd-image.png', { type: blob.type || 'image/png' });
    if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: 'SD Pocket 作品' });
    else showToast('当前浏览器不支持直接分享，请先下载');
  } catch (error) {
    showToast('分享失败，请先下载图片');
  }
});

const IDEAS = [
  '雨后的东京街头，霓虹灯倒映在路面，女孩撑着透明雨伞，电影感构图',
  '清晨的森林小屋，薄雾穿过松树，窗户透出温暖灯光，童话绘本风格',
  '未来城市的高空列车，落日映照玻璃建筑，宏大科幻概念艺术',
];
randomIdeaBtn.addEventListener('click', () => {
  nlInput.value = IDEAS[Math.floor(Math.random() * IDEAS.length)];
  nlInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
  showToast('已换一个灵感');
});

function showLogin() {
  app.classList.add('hidden');
  actionDock.classList.add('hidden');
  loginView.classList.remove('hidden');
}

function showApp(username) {
  currentUser.textContent = username;
  loginView.classList.add('hidden');
  app.classList.remove('hidden');
  actionDock.classList.remove('hidden');
  loadHistory();
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginError.textContent = '';
  const submit = loginForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  submit.textContent = '登录中…';
  try {
    const resp = await fetch(`${API}/api/login`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ username: usernameInput.value.trim(), password: passwordInput.value }),
    });
    if (!resp.ok) {
      loginError.textContent = await readError(resp, '登录失败');
      return;
    }
    const data = await resp.json();
    passwordInput.value = '';
    showApp(data.username);
  } catch (_) {
    loginError.textContent = '无法连接服务器';
  } finally {
    submit.disabled = false;
    submit.textContent = '登录';
  }
});

logoutBtn.addEventListener('click', async () => {
  await fetch(`${API}/api/logout`, { method: 'POST', headers: authHeaders() });
  historyList.replaceChildren();
  showLogin();
});

async function initialize() {
  applyResolution(960, 1280);
  updateAdvSummary();
  try {
    const resp = await fetch(`${API}/api/me`, { headers: authHeaders() });
    if (resp.ok) showApp((await resp.json()).username);
    else showLogin();
  } catch (_) {
    showLogin();
  }
}

initialize();
