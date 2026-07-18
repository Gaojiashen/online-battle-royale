// player_panel.js — Player Panel entry, homepage, return-to-panel
// 依赖: state.js, common/ui.js, player_modules.js
async function enterHome() {
  const name = document.getElementById('input-name').value.trim();
  if (!name) return;
  PlayerState.setPlayer(name);

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
    const resp = await fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/battles`);
    const data = await resp.json();
    if (!data.ok) { showError('获取战斗列表失败'); return; }
    renderHome(data);
  } catch (e) {
    showError('加载主页失败: ' + e.message);
  }
}

function renderHome(data) {
  document.getElementById('home-title').textContent = `${data.player_name} 的玩家面板`;
  renderModules();
}

function renderModules() {
  const container = document.getElementById('player-modules');
  container.innerHTML = PlayerModules.map(m => {
    const cls = m.enabled ? 'module-active' : 'module-locked';
    const onclick = m.enabled ? `onclick="ModuleManager.open('${m.id}', this)"` : '';
    const cursor = m.enabled ? 'cursor:pointer;' : '';
    return `<div class="module-card ${cls}" ${onclick} style="${cursor}">
      <div class="module-icon">${m.icon}</div>
      <div class="module-name">${m.name}</div>
      <div class="module-desc">${m.desc}</div>
    </div>`;
  }).join('');
}

async function returnToPanel(btn) {
  if (btn) setBtnLoading(btn, '返回中...');
  stopPolling();
  disconnectBattleWebSocket();
  PlayerState.clearBattle();
  document.getElementById('section-replay').classList.add('hidden');
  document.getElementById('section-battle').classList.add('hidden');
  document.getElementById('section-battle-module').classList.add('hidden');
  document.getElementById('section-home').classList.remove('hidden');
  await loadHome();
  if (btn) resetBtn(btn);
}
