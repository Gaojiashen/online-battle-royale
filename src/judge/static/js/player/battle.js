// battle.js — Battle Dashboard: refresh, deck, submit, end screen, logs
// 依赖: state.js, common/ui.js

// ═══════════════════════════════════════
// WebSocket (Phase 3: 实时推送)
// ═══════════════════════════════════════
let battleSocket = null;
let wsConnected = false;
let wsReconnectTimer = null;
let wsPingInterval = null;
let refreshSeq = 0;
const WS_RECONNECT_DELAY = 5000;

// ── beforeunload 保底清理 ──
let _beforeunloadRegistered = false;
if (!_beforeunloadRegistered) {
  _beforeunloadRegistered = true;
  window.addEventListener('beforeunload', function () {
    disconnectBattleWebSocket();
  });
}

function connectBattleWebSocket(battleId) {
  if (battleSocket) { disconnectBattleWebSocket(); }
  if (!battleId) return;

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${location.host}/ws/battle/${battleId}`;

  try {
    battleSocket = new WebSocket(wsUrl);
  } catch (e) {
    console.debug('[WS] create failed:', e.message);
    startFallbackPolling();
    return;
  }

  battleSocket.onopen = function () {
    wsConnected = true;
    console.debug('[WS] connected');
    stopPolling();
    // 每 30 秒发送 ping 保活（先清理旧的）
    if (wsPingInterval) { clearInterval(wsPingInterval); }
    wsPingInterval = setInterval(function () {
      if (battleSocket && battleSocket.readyState === WebSocket.OPEN) {
        battleSocket.send('ping');
      } else {
        if (wsPingInterval) { clearInterval(wsPingInterval); wsPingInterval = null; }
      }
    }, 30000);
  };

  battleSocket.onmessage = function (msg) {
    try {
      var event = JSON.parse(msg.data);
      console.debug('[WS] message', event.type);
      // 收到推送后调用 refreshAll 获取完整状态
      refreshAll();
    } catch (e) {
      console.debug('[WS] parse error:', e.message);
    }
  };

  battleSocket.onclose = function () {
    wsConnected = false;
    // 清理 ping timer
    if (wsPingInterval) { clearInterval(wsPingInterval); wsPingInterval = null; }
    // 防止 disconnect 后的 onclose 触发 reconnect
    if (!battleSocket) { console.debug('[WS] close after disconnect, skip'); return; }
    console.debug('[WS] closed, fallback to polling');
    startFallbackPolling();
    scheduleReconnect(battleId);
  };

  battleSocket.onerror = function () {
    // onclose will fire after onerror, cleanup there
    console.debug('[WS] error');
  };
}

function disconnectBattleWebSocket() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if (wsPingInterval) {
    clearInterval(wsPingInterval);
    wsPingInterval = null;
  }
  if (battleSocket) {
    var sock = battleSocket;  // 保存局部引用
    battleSocket = null;      // 先置空，onclose 检查时会跳过
    sock.onclose = null;
    sock.close();
  }
  wsConnected = false;
}

function scheduleReconnect(battleId) {
  if (wsReconnectTimer) return;
  console.debug('[WS] reconnect in ' + (WS_RECONNECT_DELAY / 1000) + 's');
  wsReconnectTimer = setTimeout(function () {
    wsReconnectTimer = null;
    if (!wsConnected && PlayerState.currentBattleId) {
      connectBattleWebSocket(PlayerState.currentBattleId);
    }
  }, WS_RECONNECT_DELAY);
}

function startFallbackPolling() {
  // 根据当前状态选择合适的 polling 间隔
  // 简单起见用 3000ms，refreshAll 内部会调整
  startPolling(3000);
}

// ═══════════════════════════════════════
// Refresh
// ═══════════════════════════════════════
async function refreshAll() {
  var currentSeq = ++refreshSeq;
  try {
    const resp = await fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/battle-full?battle_id=${encodeURIComponent(PlayerState.currentBattleId)}`);
    if (!resp.ok) { showError('获取战斗状态失败'); return; }
    const data = await resp.json();
    // 防止旧响应覆盖新状态（竞态保护）
    if (currentSeq !== refreshSeq) { console.debug('[WS] ignore stale refresh #' + currentSeq); return; }
    PlayerState.currentState = data.state;
    PlayerState.mySide = data.my_side;
    document.getElementById('status-title').textContent = `⚔ ${PlayerState.playerName} 的 战场`;
    renderBattleStatus(data);
    document.getElementById('last-update').textContent = now();

    const inDeckPhase = (data.state === '已初始化' || data.state === '选牌中') && !data.deck_locked;
    const inBattle = data.state === '对战中';
    const finished = data.state === '已结束';

    document.getElementById('battle-deck').classList.toggle('hidden', !inDeckPhase);
    document.getElementById('battle-submit').classList.toggle('hidden', !inBattle);
    document.getElementById('battle-end').classList.toggle('hidden', !finished);
    document.getElementById('battle-logs').classList.toggle('hidden', !inBattle && !finished);

    if (inDeckPhase) loadAvailableCardsInline(data.cards);
    if (inBattle) loadBattleSubmit(data);
    if (finished) renderEndScreen(data);
    if (inBattle || finished) loadBattleLogsInline(data.logs);

    if (inDeckPhase && data.deck_confirmed) {
      document.getElementById('confirmed-deck-area').classList.remove('hidden');
      renderDeckCards('confirmed-deck-list', data.my_deck, true);
    } else {
      document.getElementById('confirmed-deck-area').classList.add('hidden');
    }

    stopPolling();
    // WebSocket 连接时不启用 polling
    if (wsConnected) return;
    if (inDeckPhase && data.deck_confirmed && !data.deck_locked) {
      startPolling(3000);
    } else if (inBattle && data.my_submitted_this_round) {
      startPolling(2000);
    }
  } catch(e) {
    showError('刷新失败: ' + e.message);
  }
}

function startPolling(ms) {
  stopPolling();
  PlayerState.pollTimer = setInterval(refreshAll, ms);
}
function stopPolling() {
  if (PlayerState.pollTimer) { clearInterval(PlayerState.pollTimer); PlayerState.pollTimer = null; }
}

// ═══════════════════════════════════════
// Battle status UI
// ═══════════════════════════════════════
function hpColor(hp) {
  if (hp > 12) return 'green';
  if (hp > 6) return 'yellow';
  return 'red';
}
function renderBattleStatus(data) {
  let displayState = data.state;
  if (data.state === '对战中') {
    displayState = data.my_submitted_this_round ? '等待对方出牌' : '待出牌';
  } else if (data.state === '已初始化' || data.state === '选牌中') {
    displayState = '选牌中';
  }
  let html = '';
  html += renderHPBar(PlayerState.playerName, data.my_hp);
  html += '<div class="vs-divider">VS</div>';
  html += renderHPBar(data.opponent_name, data.opponent_hp);
  html += `<div style="text-align:center;margin-top:8px;color:#888;">当前回合：${data.current_round} · ${displayState}</div>`;
  document.getElementById('status-body').innerHTML = html;

  const r = data.my_resources || {};
  document.getElementById('my-resources').innerHTML =
    `锋芒:${r.edge||0} 幻影:${r.phantom||0} 蓄力:${r.charge||0} 寒意:${r.chill||0} 脉动:${r.pulse||0} 洞悉:${r.read||0} 看破:${r.insight||0}`;
}
function renderHPBar(name, hp) {
  return `<div class="hp-bar-row">
    <span class="name">${name||'?'}</span>
    <div class="hp-bar-outer"><div class="hp-bar-inner ${hpColor(hp)}" style="width:${hp/20*100}%"></div></div>
    <span class="hp-text">${hp} / 20</span>
  </div>`;
}

// ═══════════════════════════════════════
// Deck display
// ═══════════════════════════════════════
function cardDetailHtml(c, showEffect) {
  return `<div class="deck-card">
    <div class="dc-id">${c.card_id||''}</div>
    <div class="dc-name">${c.name||''}</div>
    <div class="dc-info">${c.category||''} · ${c.aspect||''} · Lv${c.level_requirement||0}</div>
    ${showEffect && c.effect_text ? `<div class="dc-effect">${c.effect_text}</div>` : ''}
  </div>`;
}
function renderDeckCards(containerId, cards, showEffect) {
  document.getElementById(containerId).innerHTML = cards.map(c => cardDetailHtml(c, showEffect)).join('');
}

// ═══════════════════════════════════════
// Deck selection
// ═══════════════════════════════════════
async function loadAvailableCards(showLoading = true) {
  if (showLoading) {
    document.getElementById('card-list').innerHTML = '<div style="color:#888;text-align:center;padding:20px;">加载中...</div>';
  }
  try {
    const resp = await fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/available-cards?battle_id=${encodeURIComponent(PlayerState.currentBattleId)}`);
    const data = await resp.json();
    PlayerState.availableCardsData = data.cards;
    PlayerState.selectedCards = data.cards.filter(c => c.selected).map(c => c.card_id);
    document.getElementById('deck-count').textContent = `已选择：${PlayerState.selectedCards.length} 张（最多 8 张）`;
    updateConfirmBtn();

    document.getElementById('card-list').innerHTML = data.cards.map(c => {
      const sel = PlayerState.selectedCards.includes(c.card_id);
      return `<div class="card-row${sel?' selected':''}" onclick="toggleCard('${c.card_id}',this)" data-cid="${c.card_id}">
        <div class="check">${sel?'✓':''}</div>
        <div class="cinfo">
          <div class="cname">${c.name}</div>
          <div class="cdetail">${c.category} · ${c.aspect} · ${c.effect_text||''}</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    document.getElementById('card-list').innerHTML = '<div style="color:#F44336;text-align:center;padding:20px;">加载失败，请刷新</div>';
  }
}
function toggleCard(cid, el) {
  const idx = PlayerState.selectedCards.indexOf(cid);
  if (idx >= 0) { PlayerState.selectedCards.splice(idx, 1); el.classList.remove('selected'); el.querySelector('.check').textContent = ''; }
  else if (PlayerState.selectedCards.length < 8) { PlayerState.selectedCards.push(cid); el.classList.add('selected'); el.querySelector('.check').textContent = '✓'; }
  document.getElementById('deck-count').textContent = `已选择：${PlayerState.selectedCards.length} 张（最多 8 张）`;
  updateConfirmBtn();
}
function updateConfirmBtn() {
  document.getElementById('btn-confirm-deck').disabled = (PlayerState.selectedCards.length === 0);
}
async function confirmDeck() {
  if (PlayerState.selectedCards.length === 0 || PlayerState.selectedCards.length > 8) return;
  const btn = document.getElementById('btn-confirm-deck');
  setBtnLoading(btn, '确认中...');
  try {
    const resp = await fetch('/api/player/select-deck', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({player_name: PlayerState.playerName, battle_id: PlayerState.currentBattleId, card_ids: PlayerState.selectedCards})
    });
    const data = await resp.json();
    if (!data.ok) {
      resetBtn(btn);
      showError(data.message || '确认牌库失败，请重试');
      return;
    }
    if (data.status === 'waiting_for_opponent') {
      btn.textContent = '等待对手确认中...';
      document.getElementById('confirmed-deck-area').classList.remove('hidden');
      const myCards = PlayerState.availableCardsData.filter(c => PlayerState.selectedCards.includes(c.card_id));
      renderDeckCards('confirmed-deck-list', myCards, true);
      startPolling(3000);
    } else {
      stopPolling();
      await refreshAll();
    }
  } catch (e) {
    console.error('confirmDeck error:', e);
    resetBtn(btn);
    showError('网络异常，请稍后重试');
  }
}

// ═══════════════════════════════════════
// Card submit
// ═══════════════════════════════════════
async function loadBattleSubmit(data) {
  const myDeck = data.my_deck || [];
  const oppDeck = data.opponent_deck || [];
  const sel = document.getElementById('card-select');
  sel.innerHTML = myDeck.map(c => `<option value="${c.card_id}">${c.name}</option>`).join('');

  renderDeckCards('my-battle-deck-list', myDeck, true);
  document.getElementById('opponent-battle-deck-area').classList.toggle('hidden', oppDeck.length === 0);
  if (oppDeck.length > 0) renderDeckCards('opponent-battle-deck-list', oppDeck, false);

  if (data.my_submitted_this_round) {
    sel.disabled = true;
    document.getElementById('btn-submit-card').disabled = true;
    document.getElementById('waiting-msg').classList.remove('hidden');
    document.getElementById('waiting-msg').textContent = '⏳ 本回合已提交，等待对手中...';
  } else {
    sel.disabled = false;
    const submitBtn = document.getElementById('btn-submit-card');
    submitBtn.disabled = false;
    submitBtn.textContent = '提交出牌';
    document.getElementById('waiting-msg').classList.add('hidden');
  }
}
async function submitCard() {
  const cardId = document.getElementById('card-select').value;
  if (!cardId) return;
  const btn = document.getElementById('btn-submit-card');
  setBtnLoading(btn, '提交中...');
  document.getElementById('card-select').disabled = true;
  try {
    const resp = await fetch('/api/player/submit-card', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({player_name: PlayerState.playerName, battle_id: PlayerState.currentBattleId, round_number:0, card_id:cardId})
    });
    const data = await resp.json();
    if (!data.ok) {
      resetBtn(btn);
      document.getElementById('card-select').disabled = false;
      showError(data.detail || data.message || '提交失败');
      return;
    }
    if (data.status === 'waiting_for_opponent') {
      btn.textContent = '已提交';
      document.getElementById('waiting-msg').classList.remove('hidden');
      document.getElementById('waiting-msg').textContent = '⏳ 本回合已提交，等待对手中...';
      await refreshAll();
    } else {
      await refreshAll();
    }
  } catch (e) {
    console.error('submitCard error:', e);
    resetBtn(btn);
    document.getElementById('card-select').disabled = false;
    showError('网络异常，请稍后重试');
  }
}

// ═══════════════════════════════════════
// End screen
// ═══════════════════════════════════════
function renderEndScreen(data) {
  const w = data.winner;
  let cls = 'draw', emoji = '🤝', txt = '平局！';
  if (w === PlayerState.playerName || (PlayerState.mySide === 'A' && w === 'a') || (PlayerState.mySide === 'B' && w === 'b')) {
    cls = 'win'; emoji = '🏆'; txt = `${PlayerState.playerName} 获胜！`;
  } else if (w && w !== 'draw') {
    cls = 'lose'; emoji = '💀'; txt = `${data.opponent_name} 获胜！`;
  }
  document.getElementById('battle-end').innerHTML =
    `<div class="result-msg ${cls}"><div class="big">${emoji} ${txt}</div></div>` +
    renderHPBar(PlayerState.playerName, data.my_hp) + '<div class="vs-divider">VS</div>' + renderHPBar(data.opponent_name||'对手', data.opponent_hp) +
    `<div style="text-align:center;margin-top:8px;color:#888;">总回合数：${data.current_round}</div>` +
    `<div style="text-align:center;margin-top:16px;">
      <button class="btn btn-go" onclick="returnToPanel(this)">返回玩家面板</button>
    </div>`;
}

// ═══════════════════════════════════════
// Inline renderers (from battle-full aggregated data)
// ═══════════════════════════════════════
function loadAvailableCardsInline(cards) {
  PlayerState.availableCardsData = cards;
  PlayerState.selectedCards = cards.filter(c => c.selected).map(c => c.card_id);
  document.getElementById('deck-count').textContent = `已选择：${PlayerState.selectedCards.length} 张（最多 8 张）`;
  updateConfirmBtn();
  document.getElementById('card-list').innerHTML = cards.map(c => {
    const sel = PlayerState.selectedCards.includes(c.card_id);
    return `<div class="card-row${sel?' selected':''}" onclick="toggleCard('${c.card_id}',this)" data-cid="${c.card_id}">
      <div class="check">${sel?'✓':''}</div>
      <div class="cinfo">
        <div class="cname">${c.name}</div>
        <div class="cdetail">${c.category} · ${c.aspect} · ${c.effect_text||''}</div>
      </div>
    </div>`;
  }).join('');
}

function loadBattleLogsInline(logs) {
  if (!logs || logs.length === 0) {
    document.getElementById('logs-body').innerHTML = '<div style="color:#666;">暂无记录</div>';
    return;
  }
  document.getElementById('logs-body').innerHTML = logs.map(l => {
    const mc = l.my_card || {};
    const oc = l.opponent_card || {};
    const myName = mc.card_id ? `${mc.card_id} ${mc.name}` : (mc.name || '?');
    const oppName = oc.card_id ? `${oc.card_id} ${oc.name}` : (oc.name || '?');
    return `<div class="log-entry">
      <span class="lrnd">R${l.round}</span>
      <span class="lsep">|</span>
      ${myName} vs ${oppName}
      <span class="lsep">|</span>
      ${l.rps_description||''}
    </div>`;
  }).join('');
}

// ═══════════════════════════════════════
// Battle logs (standalone, for deferred loading)
// ═══════════════════════════════════════
async function loadBattleLogs(showLoading = true) {
  if (showLoading) {
    document.getElementById('logs-body').innerHTML = '<div style="color:#888;text-align:center;padding:12px;">加载中...</div>';
  }
  try {
    const resp = await fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/battle-logs?battle_id=${encodeURIComponent(PlayerState.currentBattleId)}`);
    const data = await resp.json();
    if (!data.logs || data.logs.length === 0) {
      document.getElementById('logs-body').innerHTML = '<div style="color:#666;">暂无记录</div>';
      return;
    }
    document.getElementById('logs-body').innerHTML = data.logs.map(l => {
      const mc = l.my_card || {};
      const oc = l.opponent_card || {};
      const myName = typeof mc === 'string' ? mc : (mc.card_id ? `${mc.card_id} ${mc.name}` : (mc.name || '?'));
      const oppName = typeof oc === 'string' ? oc : (oc.card_id ? `${oc.card_id} ${oc.name}` : (oc.name || '?'));
      return `<div class="log-entry">
        <span class="lrnd">R${l.round}</span>
        <span class="lsep">|</span>
        ${myName} vs ${oppName}
        <span class="lsep">|</span>
        ${l.rps_description||''}
      </div>`;
    }).join('');
  } catch (e) {
    document.getElementById('logs-body').innerHTML = '<div style="color:#F44336;text-align:center;padding:12px;">加载日志失败</div>';
  }
}
