// player_panel.js — Player Panel entry, homepage, return-to-panel
// ═══════════════════════════════════════
// Global State
// ═══════════════════════════════════════
let playerName = '';
let battleId = '';
let currentBattleId = '';
let mySide = '';
let currentState = '';
let pollTimer = null;
let availableCardsData = [];
let selectedCards = [];

// ═══════════════════════════════════════
// Helpers
// ═══════════════════════════════════════
function setBtnLoading(btn, text) {
  btn._origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = text;
}
function resetBtn(btn) {
  btn.disabled = false;
  if (btn._origText) btn.textContent = btn._origText;
}

function showError(msg) {
  const el = document.getElementById('error-bar');
  el.textContent = msg; el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 6000);
}

function now() { return new Date().toLocaleTimeString(); }

// ═══════════════════════════════════════
// Entry
// ═══════════════════════════════════════
async function enterHome() {
  const name = document.getElementById('input-name').value.trim();
  if (!name) return;
  playerName = name;

  const btn = document.querySelector('#section-entry .btn-go');
  setBtnLoading(btn, '查询中...');
  try {
    const resp = await fetch(`/api/player/lookup?name=${encodeURIComponent(name)}`);
    const data = await resp.json();
    if (!data.ok) {
      document.getElementById('entry-err').textContent = data.message || '未找到玩家';
      document.getElementById('entry-err').classList.remove('hidden');
      resetBtn(btn);
      return;
    }
    document.getElementById('section-entry').classList.add('hidden');
    document.getElementById('section-home').classList.remove('hidden');
    await loadHome();
  } catch (e) {
    console.error('enterHome error:', e);
    resetBtn(btn);
    document.getElementById('entry-err').textContent = '网络异常，请稍后重试';
    document.getElementById('entry-err').classList.remove('hidden');
  }
}

async function loadHome() {
  try {
    const resp = await fetch(`/api/player/${encodeURIComponent(playerName)}/battles`);
    const data = await resp.json();
    if (!data.ok) { showError('获取战斗列表失败'); return; }
    renderHome(data);
  } catch (e) {
    showError('加载主页失败: ' + e.message);
  }
}

function renderHome(data) {
  document.getElementById('home-title').textContent = `${data.player_name} 的玩家面板`;
}

async function returnToPanel(btn) {
  if (btn) setBtnLoading(btn, '返回中...');
  stopPolling();
  currentBattleId = '';
  document.getElementById('section-replay').classList.add('hidden');
  document.getElementById('section-battle').classList.add('hidden');
  document.getElementById('section-battle-module').classList.add('hidden');
  document.getElementById('section-home').classList.remove('hidden');
  await loadHome();
  if (btn) resetBtn(btn);
}
