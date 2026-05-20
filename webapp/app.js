/**
 * PayRonin Mini App v2
 */
const tg = window.Telegram?.WebApp;
const API = '/api';

let state = {
  user: null, balance: 0, services: {}, purchases: [], topupPackages: [],
  order: { service: null, duration: null, price: 0 },
};

document.addEventListener('DOMContentLoaded', async () => {
  if (tg) { tg.ready(); tg.expand(); tg.setHeaderColor('#0f0f0f'); tg.setBackgroundColor('#0f0f0f'); }
  setupNav();
  showScreen('home');
  await loadData();
});

function setupNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => showScreen(item.dataset.screen));
  });
}

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const screen = document.getElementById('screen-' + name);
  const nav = document.querySelector('.nav-item[data-screen="' + name + '"]');
  if (screen) screen.classList.add('active');
  if (nav) nav.classList.add('active');
  if (name === 'history') renderHistory();
  if (name === 'topup') renderTopup();
}

function getHeaders() { return { 'Content-Type': 'application/json', 'X-Init-Data': tg ? tg.initData : '' }; }

async function apiFetch(path) {
  try {
    var r = await fetch(API + path, { headers: getHeaders() });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } catch(e) { console.error('API:', e); return null; }
}

async function loadData() {
  showLoading('home');
  var results = await Promise.all([apiFetch('/me'), apiFetch('/services'), apiFetch('/topup_packages')]);
  var me = results[0], services = results[1], packages = results[2];
  if (me && !me.error) { state.user = me; state.balance = me.balance; state.purchases = me.purchases || []; }
  if (services) state.services = services;
  if (packages) state.topupPackages = packages;
  renderHome();
  renderServicesScreen();
}

async function refreshBalance() {
  var me = await apiFetch('/me');
  if (me && !me.error) { state.balance = me.balance; state.purchases = me.purchases || []; }
}

// ── Главная ─────────────────────────────────────────────────
function renderHome() {
  var el = document.getElementById('screen-home');
  var name = state.user ? state.user.first_name : 'Пользователь';
  el.innerHTML =
    '<div class="header"><h1>👋 ' + esc(name) + '</h1><p>Добро пожаловать в магазин</p></div>' +
    '<div class="balance-card">' +
    '<div class="balance-label">Ваш баланс</div>' +
    '<div class="balance-amount">' + state.balance + ' ⭐</div>' +
    '<div class="balance-sub">' + state.purchases.length + ' покупок</div>' +
    '</div>' +
    '<button class="btn btn-primary btn-block" onclick="showScreen(\'topup\')">💰 Пополнить баланс</button>' +
    '<div class="section-title" style="margin-top:24px">🔥 Популярные услуги</div>' +
    '<div class="services-grid" id="popular-services"></div>';

  var pop = document.getElementById('popular-services');
  var keys = Object.keys(state.services).slice(0, 4);
  var html = '';
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i], s = state.services[k];
    var mp = 999; for (var j = 0; j < s.prices.length; j++) { if (s.prices[j].price < mp) mp = s.prices[j].price; }
    html += '<div class="service-card" onclick="openService(\'' + k + '\')">' +
      '<div class="emoji">' + s.emoji + '</div>' +
      '<div class="name">' + esc(s.name) + '</div>' +
      '<div class="price-tag">от ' + mp + ' ⭐</div></div>';
  }
  pop.innerHTML = html;
}

// ── Список услуг ────────────────────────────────────────────
function renderServicesScreen() {
  var el = document.getElementById('services-list');
  if (!el) return;
  var keys = Object.keys(state.services);
  var html = '';
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i], s = state.services[k];
    var mp = 999; for (var j = 0; j < s.prices.length; j++) { if (s.prices[j].price < mp) mp = s.prices[j].price; }
    html += '<div class="list-item" onclick="openService(\'' + k + '\')" style="cursor:pointer">' +
      '<div class="emoji">' + s.emoji + '</div>' +
      '<div class="info"><div class="title">' + esc(s.name) + '</div><div class="sub">' + esc(s.description) + '</div></div>' +
      '<div class="price">от ' + mp + ' ⭐</div></div>';
  }
  el.innerHTML = html;
}

// ── Услуга ──────────────────────────────────────────────────
function openService(key) {
  var s = state.services[key];
  if (!s) return;
  state.order = { service: key, duration: null, price: 0 };
  var screen = document.getElementById('screen-services');

  if (s.no_duration && s.prices.length > 0) {
    state.order.duration = s.prices[0].duration_key;
    state.order.price = s.prices[0].price;
  }

  var durHtml = '';
  if (!s.no_duration) {
    durHtml = '<div class="section-title">Выберите срок</div><div class="duration-grid">';
    for (var i = 0; i < s.prices.length; i++) {
      var p = s.prices[i];
      durHtml += '<div class="dur-btn" onclick="selDur(\'' + key + '\',\'' + p.duration_key + '\',' + p.price + ')" id="dur-' + p.duration_key + '">' +
        '<div class="dur-label">' + esc(p.duration_label) + '</div><div class="dur-price">' + p.price + ' ⭐</div></div>';
    }
    durHtml += '</div>';
  }

  var inputHtml = '';
  if (s.needs_target) {
    inputHtml += '<div class="input-group"><label>👤 Пользователь (@username или ID)</label>' +
      '<input type="text" id="inp-target" placeholder="@username или 123456789"></div>';
  }
  if (key === 'prefix') {
    inputHtml += '<div class="input-group"><label>🏷 Текст префикса (до 16 символов)</label>' +
      '<input type="text" id="inp-text" maxlength="16" placeholder="VIP"></div>';
  }
  if (s.needs_text && key !== 'prefix') {
    inputHtml += '<div class="input-group"><label>📝 Текст</label>' +
      '<textarea id="inp-text" rows="3" maxlength="255" placeholder="Введите текст..."></textarea></div>';
  }
  if (key === 'pin') {
    inputHtml += '<div class="input-group"><label>📌 ID сообщения</label>' +
      '<input type="number" id="inp-msgid" placeholder="12345"></div>';
  }

  var initPrice = s.no_duration ? s.prices[0].price : '?';
  screen.innerHTML =
    '<div class="header"><h1>' + s.emoji + ' ' + esc(s.name) + '</h1><p>' + esc(s.description) + '</p></div>' +
    durHtml + inputHtml +
    '<div id="buy-section" style="' + (s.no_duration ? '' : 'display:none;') + 'margin-top:20px">' +
    '<div style="text-align:center;margin-bottom:12px"><span style="font-size:24px;font-weight:800" id="sel-price">' + initPrice + ' ⭐</span></div>' +
    '<div id="buy-status"></div>' +
    '<button class="btn btn-primary btn-block" id="buy-btn" onclick="doBuy()">💰 Купить — ' + initPrice + ' ⭐</button>' +
    '<p style="text-align:center;margin-top:8px;font-size:12px;color:var(--text-muted)">Баланс: ' + state.balance + ' ⭐</p></div>' +
    '<button class="btn btn-secondary" style="margin-top:16px" onclick="backToServices()">⬅️ Назад</button>';
}

function selDur(key, durKey, price) {
  state.order.duration = durKey;
  state.order.price = price;
  var btns = document.querySelectorAll('.dur-btn');
  for (var i = 0; i < btns.length; i++) btns[i].classList.remove('selected');
  var el = document.getElementById('dur-' + durKey);
  if (el) el.classList.add('selected');
  document.getElementById('buy-section').style.display = 'block';
  document.getElementById('sel-price').textContent = price + ' ⭐';

  var buyBtn = document.getElementById('buy-btn');
  buyBtn.textContent = '💰 Купить — ' + price + ' ⭐';

  var st = document.getElementById('buy-status');
  if (state.balance < price) {
    st.innerHTML = '<div style="background:rgba(255,107,107,.15);border:1px solid var(--red);border-radius:8px;padding:12px;margin-bottom:12px;text-align:center;font-size:13px;">' +
      '❌ Недостаточно звёзд (нужно ' + price + ', у вас ' + state.balance + ')<br><br>' +
      '<span onclick="showScreen(\'topup\')" style="color:var(--accent-light);cursor:pointer;text-decoration:underline;">Пополнить →</span></div>';
  } else { st.innerHTML = ''; }
}

async function doBuy() {
  var service = state.order.service, duration = state.order.duration, price = state.order.price;
  var s = state.services[service];
  if (!duration) { showToast('Выберите срок', 'error'); return; }
  if (state.balance < price) { showToast('❌ Недостаточно звёзд!', 'error'); showScreen('topup'); return; }

  var body = { service: service, duration_key: duration };
  if (s.needs_target) {
    var v = document.getElementById('inp-target'); v = v ? v.value.trim() : '';
    if (!v) { showToast('Укажите пользователя', 'error'); return; }
    body.target = v;
  }
  if (service === 'prefix' || (s.needs_text && service !== 'prefix')) {
    var t = document.getElementById('inp-text'); t = t ? t.value.trim() : '';
    if (!t) { showToast('Введите текст', 'error'); return; }
    body.text = t;
  }
  if (service === 'pin') {
    var m = document.getElementById('inp-msgid'); m = m ? m.value.trim() : '';
    if (!m) { showToast('Укажите ID сообщения', 'error'); return; }
    body.message_id = parseInt(m);
  }

  var btn = document.getElementById('buy-btn');
  btn.disabled = true; btn.textContent = '⏳ Применяю...';

  try {
    var res = await fetch(API + '/buy', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) });
    var data = await res.json();
    await refreshBalance();
    var st = document.getElementById('buy-status');

    if (data.ok) {
      st.innerHTML = '<div style="background:rgba(0,206,201,.15);border:1px solid var(--green);border-radius:12px;padding:20px;margin-bottom:12px;text-align:center;">' +
        '<div style="font-size:36px;margin-bottom:8px;">✅</div>' +
        '<div style="font-weight:700;font-size:16px;margin-bottom:4px;">' + data.service_emoji + ' ' + esc(data.service_name) + '</div>' +
        '<div style="font-size:14px;margin-bottom:8px;">' + esc(data.result) + '</div>' +
        '<div style="font-size:13px;color:var(--text-dim);">Срок: ' + esc(data.duration_label) + ' · Списано: ' + data.price + ' ⭐</div>' +
        '<div style="font-size:13px;color:var(--text-dim);margin-top:4px;">Баланс: ' + data.balance + ' ⭐</div></div>' +
        '<button class="btn btn-secondary btn-block" onclick="backToServices()" style="margin-top:8px">🛒 Купить ещё</button>';
      btn.style.display = 'none';
      showToast('✅ Услуга применена!', 'success');
    } else {
      var errMsg = data.error || 'Ошибка';
      st.innerHTML = '<div style="background:rgba(255,107,107,.15);border:1px solid var(--red);border-radius:12px;padding:16px;margin-bottom:12px;text-align:center;">' +
        '<div style="font-size:28px;margin-bottom:8px;">⚠️</div><div style="font-size:14px;">' + esc(errMsg) + '</div>' +
        (data.refunded ? '<div style="font-size:12px;color:var(--green);margin-top:6px;">💰 Звёзды возвращены</div>' : '') + '</div>';
      btn.disabled = false; btn.textContent = '💰 Попробовать — ' + price + ' ⭐';
      showToast(errMsg, 'error');
    }
  } catch(e) {
    showToast('❌ Ошибка сети', 'error');
    btn.disabled = false; btn.textContent = '💰 Купить — ' + price + ' ⭐';
  }
}

function backToServices() {
  var screen = document.getElementById('screen-services');
  screen.innerHTML = '<div class="header"><h1>🛒 Все услуги</h1><p>Выберите услугу</p></div><div id="services-list"></div>';
  renderServicesScreen();
}

// ── Пополнение ──────────────────────────────────────────────
function renderTopup() {
  var balEl = document.getElementById('topup-balance');
  if (balEl) balEl.textContent = state.balance + ' ⭐';
  var el = document.getElementById('topup-list');
  if (!el) return;

  var html = '';
  for (var i = 0; i < state.topupPackages.length; i++) {
    var p = state.topupPackages[i];
    var bt = p.bonus > 0 ? '+' + p.bonus + ' бонус 🎁' : '';
    html += '<div class="topup-card" data-key="' + p.key + '" data-cost="' + p.stars_cost + '" data-get="' + p.stars_get + '">' +
      '<div class="topup-left"><div class="topup-amount">' + p.stars_get + ' ⭐</div>' +
      (bt ? '<div class="topup-bonus">' + bt + '</div>' : '') + '</div>' +
      '<div class="topup-right">' + p.stars_cost + ' Stars 💎</div></div>';
  }
  el.innerHTML = html;

  // Вешаем обработчики через addEventListener (не onclick)
  var cards = el.querySelectorAll('.topup-card');
  for (var j = 0; j < cards.length; j++) {
    cards[j].addEventListener('click', handleTopupClick);
  }
}

function handleTopupClick(e) {
  var card = e.currentTarget;
  var key = card.getAttribute('data-key');
  var cost = parseInt(card.getAttribute('data-cost'));
  var get = parseInt(card.getAttribute('data-get'));
  doTopup(key, cost, get);
}

async function doTopup(key, cost, get) {
  showToast('💎 Создаю счёт...', 'success');

  try {
    var res = await fetch(API + '/topup', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ key: key, stars_cost: cost, stars_get: get })
    });
    var data = await res.json();

    if (data.ok) {
      showToast('✅ Счёт отправлен! Закройте и оплатите в чате.', 'success');
      setTimeout(function() { if (tg) tg.close(); }, 2000);
    } else {
      showToast('❌ ' + (data.error || 'Ошибка'), 'error');
    }
  } catch(e) {
    console.error('Topup error:', e);
    showToast('❌ Ошибка сети', 'error');
  }
}

// ── История ─────────────────────────────────────────────────
function renderHistory() {
  var el = document.getElementById('history-list');
  if (!el) return;
  if (!state.purchases.length) {
    el.innerHTML = '<div class="empty"><div class="icon">📜</div><p>Пока нет покупок</p></div>';
    return;
  }
  var html = '';
  for (var i = 0; i < state.purchases.length; i++) {
    var p = state.purchases[i];
    var svc = state.services[p.service];
    var emoji = svc ? svc.emoji : '❓';
    var name = svc ? svc.name : p.service;
    var date = new Date(p.created_at * 1000).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    html += '<div class="list-item"><div class="emoji">' + emoji + '</div>' +
      '<div class="info"><div class="title">' + esc(name) + '</div><div class="sub">' + date + '</div></div>' +
      '<div class="price">' + p.price_stars + ' ⭐</div></div>';
  }
  el.innerHTML = html;
}

// ── Утилиты ─────────────────────────────────────────────────
function showLoading(n) {
  var el = document.getElementById('screen-' + n);
  if (el) el.innerHTML = '<div class="loader"><div class="spinner"></div><p style="color:var(--text-dim)">Загрузка...</p></div>';
}

function showToast(text, type) {
  var t = document.getElementById('toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = text;
  t.className = 'toast ' + (type || '') + ' show';
  setTimeout(function() { t.classList.remove('show'); }, 3000);
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
