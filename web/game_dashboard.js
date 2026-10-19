'use strict';
function gameEconomyLink(label='Open game economy ↗',className='button primary',itemId=''){
  return `<a class="${className}" href="#economy" ${itemId?`data-game-economy-item="${esc(itemId)}"`:'data-game-economy'}>${esc(label)}</a>`;
}
function bindGameDashboardLinks(){
  const url=S.data?.gameDashboard?.economyUrl;
  $$('[data-game-economy],[data-game-economy-item]').forEach(link=>{
    const id=link.dataset?.gameEconomyItem;
    link.href=url?url+(id&&/^\d{1,10}$/.test(id)?'/item/'+encodeURIComponent(id):''):'#economy';
    if(url){link.target='_blank';link.rel='noopener noreferrer';link.title='Open the game’s economy dashboard';}
    else{link.removeAttribute('target');link.removeAttribute('rel');link.title='Game dashboard settings and previous Studio history';}
  });
}
async function renderGameEconomy(){
  const navigation=S.navigation;
  const data=await api('/api/game-dashboard');
  if(S.page!=='economy'||navigation!==S.navigation)return;
  S.data.gameDashboard=data;
  $('#content').innerHTML=head('GAME DASHBOARD','Economy','Currency, items and shops are available in the game’s dashboard.')+
    `<section class="panel"><div class="work-body">${data.economyUrl?gameEconomyLink():`<p class="notice">${esc(data.error)}</p>`}<p class="work-help">Start your world with its usual launcher to use the dashboard.</p></div></section>`+
    (data.archiveAvailable?`<section class="panel work-section"><div class="panel-header"><h2>Previous Studio history</h2></div><div class="work-body"><p>Your previous Studio snapshots and notes are archived separately.</p><a class="button" href="/api/economy/archive" download>Download history &amp; notes</a></div></section>`:'');
  bindGameDashboardLinks();
}
