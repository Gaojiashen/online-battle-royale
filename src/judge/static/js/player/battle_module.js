// battle_module.js — Battle Module (active + finished lists)
async function enterBattleModule() {
  document.getElementById('section-home').classList.add('hidden');
  document.getElementById('section-battle-module').classList.remove('hidden');
  try {
    const resp = await fetch(`/api/player/${encodeURIComponent(playerName)}/battles`);
    const data = await resp.json();
    if (!data.ok) { showError('获取战斗列表失败'); return; }
    renderBattleModule(data);
  } catch (e) {
    showError('加载战斗模块失败: ' + e.message);
  }
}

function renderBattleModule(data) {
  document.getElementById('battle-module-title').textContent = `⚔ ${data.player_name} 的战斗`;

  const active = data.active || [];
  const activeDiv = document.getElementById('active-battles');
  if (active.length === 0) {
    activeDiv.innerHTML = '<div style="color:#666;">暂无进行中的战斗</div>';
  } else {
    activeDiv.innerHTML = active.map(b => {
      const stateLabel = b.state === '对战中' ? '对战中' : '选牌中';
      return `<div class="battle-row">
        <div class="binfo">
          <div class="bname">vs ${b.opponent||'?'}</div>
          <div class="bmeta"><span class="badge badge-active">${stateLabel}</span> · 回合${b.total_rounds||0} · ${b.created_at||''}</div>
        </div>
        <button class="btn btn-go btn-sm" onclick="joinBattle('${b.battle_id}')">进入战斗</button>
      </div>`;
    }).join('');
  }

  const finished = data.finished || [];
  const finishedDiv = document.getElementById('finished-battles');
  if (finished.length === 0) {
    finishedDiv.innerHTML = '<div style="color:#666;">暂无历史战斗</div>';
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

async function joinBattle(bid) {
  battleId = bid;
  currentBattleId = bid;
  document.getElementById('section-battle-module').classList.add('hidden');
  document.getElementById('section-battle').classList.remove('hidden');
  await refreshAll();
}

async function viewReplay(bid) {
  const btn = document.querySelector(`button[onclick="viewReplay('${bid}')"]`);
  if (btn) setBtnLoading(btn, '加载中...');
  currentBattleId = bid;
  document.getElementById('section-battle-module').classList.add('hidden');
  document.getElementById('section-replay').classList.remove('hidden');
  await loadReplay(bid);
  if (btn) resetBtn(btn);
}
