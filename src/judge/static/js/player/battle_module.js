// battle_module.js — Battle Module (active + finished lists)
// 依赖: state.js, common/ui.js, battle.js, replay.js, module_manager.js
const LOADING_HTML = '<div style="color:#888;text-align:center;padding:20px;">加载中...</div>';
const ERROR_HTML = '<div style="color:#F44336;text-align:center;padding:20px;">加载失败，请重试</div>';

function exitBattleModule() {
  stopPolling();
  document.getElementById('section-battle-module').classList.add('hidden');
}

function _setBattleSections(html) {
  document.getElementById('active-battles').innerHTML = html;
  document.getElementById('finished-battles').innerHTML = html;
}

async function enterBattleModule(btn) {
  if (btn) UI.setLoading(btn, '加载中...');
  document.getElementById('section-home').classList.add('hidden');
  document.getElementById('section-battle-module').classList.remove('hidden');
  _setBattleSections(LOADING_HTML);
  try {
    const resp = await fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/battles`);
    const data = await resp.json();
    if (!data.ok) {
      _setBattleSections(ERROR_HTML);
      showError('获取战斗列表失败');
      return;
    }
    renderBattleModule(data);
  } catch (e) {
    _setBattleSections(ERROR_HTML);
    showError('加载战斗模块失败: ' + e.message);
  } finally {
    if (btn) UI.clearLoading(btn);
  }
}

function renderBattleModule(data) {
  document.getElementById('battle-module-title').textContent = `⚔ ${data.player_name} 的战斗`;

  const active = data.active || [];
  const activeDiv = document.getElementById('active-battles');
  if (active.length === 0) {
    activeDiv.innerHTML = '<div style="color:#666;text-align:center;padding:12px;">当前没有进行中的战斗</div>';
  } else {
    activeDiv.innerHTML = active.map(b => {
      const stateLabel = b.state === '对战中' ? '对战中' : '选牌中';
      return `<div class="battle-row">
        <div class="binfo">
          <div class="bname">vs ${b.opponent||'?'}</div>
          <div class="bmeta"><span class="badge badge-active">${stateLabel}</span> · 回合${b.total_rounds||0} · ${b.created_at||''}</div>
        </div>
        <button class="btn btn-go btn-sm" onclick="joinBattle('${b.battle_id}', this)">进入战斗</button>
      </div>`;
    }).join('');
  }

  const finished = data.finished || [];
  const finishedDiv = document.getElementById('finished-battles');
  if (finished.length === 0) {
    finishedDiv.innerHTML = '<div style="color:#666;text-align:center;padding:12px;">暂无历史战斗</div>';
  } else {
    finishedDiv.innerHTML = finished.map(b => {
      let badgeCls = 'badge-draw';
      if (b.result === '胜利') badgeCls = 'badge-win';
      else if (b.result === '失败') badgeCls = 'badge-lose';
      return `<div class="battle-row">
        <div class="binfo">
          <div class="bname">vs ${b.opponent||'?'}</div>
          <div class="bmeta"><span class="badge ${badgeCls}">${b.result}</span> · ${b.total_rounds||0}回合 · ${b.created_at||''}</div>
        </div>
        <button class="btn btn-outline btn-sm" onclick="viewReplay('${b.battle_id}')">查看回顾</button>
      </div>`;
    }).join('');
  }
}

async function joinBattle(bid, btn) {
  if (btn) UI.setLoading(btn, '进入中...');
  PlayerState.setBattle(bid);
  document.getElementById('section-battle-module').classList.add('hidden');
  document.getElementById('section-battle').classList.remove('hidden');
  try {
    await refreshAll();
  } catch (e) {
    showError('进入战斗失败: ' + e.message);
  }
  if (btn) UI.clearLoading(btn);
}

async function viewReplay(bid) {
  const btn = document.querySelector(`button[onclick="viewReplay('${bid}')"]`);
  if (btn) UI.setLoading(btn, '加载中...');
  PlayerState.currentBattleId = bid;
  document.getElementById('section-battle-module').classList.add('hidden');
  document.getElementById('section-replay').classList.remove('hidden');
  await loadReplay(bid);
  if (btn) UI.clearLoading(btn);
}
