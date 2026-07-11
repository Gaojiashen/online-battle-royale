// replay.js — Battle Replay view
// 依赖: state.js, common/ui.js
async function loadReplay(bid) {
  try {
    const [battleResp, logsResp] = await Promise.all([
      fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/battle?battle_id=${encodeURIComponent(bid)}`),
      fetch(`/api/player/${encodeURIComponent(PlayerState.playerName)}/battle-logs?battle_id=${encodeURIComponent(bid)}`)
    ]);
    const battle = await battleResp.json();
    const logs = await logsResp.json();
    renderReplay(battle, logs);
  } catch (e) {
    showError('加载回顾失败: ' + e.message);
  }
}

function renderReplay(battle, logs) {
  const opp = battle.opponent_name || '?';
  const state = battle.state || '';
  const winner = battle.winner || '';
  let result = '平局';
  if (winner === PlayerState.playerName || (battle.my_side === 'A' && winner === 'a') || (battle.my_side === 'B' && winner === 'b')) result = '胜利';
  else if (winner && winner !== 'draw') result = '失败';

  document.getElementById('replay-summary').innerHTML = `
    <div style="display:flex;gap:24px;flex-wrap:wrap;">
      <div><span style="color:#888;">对手:</span> <b>${opp}</b></div>
      <div><span style="color:#888;">结果:</span> <b>${result}</b></div>
      <div><span style="color:#888;">状态:</span> ${state}</div>
      <div><span style="color:#888;">总回合:</span> ${battle.current_round||0}</div>
    </div>`;

  const roundList = logs.logs || [];
  if (roundList.length === 0) {
    document.getElementById('replay-rounds').innerHTML = '<div style="color:#666;">暂无回合记录</div>';
    return;
  }
  document.getElementById('replay-rounds').innerHTML = roundList.map(l => {
    const mc = l.my_card || {};
    const oc = l.opponent_card || {};
    const myRes = (l.my_resource_logs || []).join(' · ');
    const oppRes = (l.opponent_resource_logs || []).join(' · ');
    const events = (l.special_events || []).join(' · ');
    return `<div class="replay-round">
      <div class="rr-header">第 ${l.round} 回合</div>
      <div class="rr-cards">
        <div class="rr-card-detail">
          <div style="color:#c9a84c;">我方</div>
          <div><b>${mc.name||'?'}</b> <span style="color:#888;">${mc.card_id||''}</span></div>
          <div style="font-size:12px;color:#aaa;">${mc.category||''} · ${mc.aspect||''} · Lv${mc.level_requirement||0}</div>
          ${mc.effect_text ? `<div style="font-size:11px;color:#999;margin-top:2px;">${mc.effect_text}</div>` : ''}
        </div>
        <div class="rr-card-detail">
          <div style="color:#F44336;">对手</div>
          <div><b>${oc.name||'?'}</b> <span style="color:#888;">${oc.card_id||''}</span></div>
          <div style="font-size:12px;color:#aaa;">${oc.category||''} · ${oc.aspect||''} · Lv${oc.level_requirement||0}</div>
          ${oc.effect_text ? `<div style="font-size:11px;color:#999;margin-top:2px;">${oc.effect_text}</div>` : ''}
        </div>
      </div>
      <div class="rr-result">
        <div>${l.rps_description||''}</div>
        <div style="margin-top:4px;">
          伤害: 我→敌 <b>${l.damage_to_opponent||0}</b> | 敌→我 <b>${l.damage_to_me||0}</b>
          &nbsp;·&nbsp; HP: 我 ${l.my_hp_after||'?'} | 敌 ${l.opponent_hp_after||'?'}
        </div>
        ${events ? `<div style="font-size:12px;color:#FF9800;margin-top:2px;">事件: ${events}</div>` : ''}
        ${myRes ? `<div style="font-size:12px;color:#aaa;margin-top:2px;">我方资源: ${myRes}</div>` : ''}
        ${oppRes ? `<div style="font-size:12px;color:#aaa;">对手资源: ${oppRes}</div>` : ''}
      </div>
    </div>`;
  }).join('');
}
