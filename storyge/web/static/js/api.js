'use strict';
/* 서버와 말하는 창구 + 아주 작은 공용 도구.
   mediaid 는 서버와 주고받을 때 항상 문자열이다 (진짜 인스타 pk 는 2^53 을 넘는다). */

async function request(method, path, payload) {
  const opts = { method: method, headers: {} };
  if (payload !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(payload);
  }
  const resp = await fetch(path, opts);
  let data = {};
  try { data = await resp.json(); } catch (ignored) { data = {}; }
  if (!resp.ok) {
    const err = new Error(data.error || ('HTTP ' + resp.status));
    err.status = resp.status;
    err.data = data;
    throw err;
  }
  return data;
}

const API = {
  reset:         ()      => request('POST', '/api/reset'),
  state:         ()      => request('GET', '/api/state'),
  fetchStart:    (b)     => request('POST', '/api/fetch', b),
  fetchState:    (id)    => request('GET', '/api/fetch/' + id),
  fetchCancel:   (id)    => request('POST', '/api/fetch/' + id + '/cancel'),
  saveStart:     (b)     => request('POST', '/api/save', b),
  saveState:     (id)    => request('GET', '/api/save/' + id),
  settings:      (b)     => request('POST', '/api/settings', b),
  checkDir:      (path)  => request('POST', '/api/settings/save_dir/check', { path: path }),
  openDir:       ()      => request('POST', '/api/settings/save_dir/open'),
  // 서버 PC 에 탐색기 창을 띄운다. 사람이 고를 때까지 기다리므로 오래 걸릴 수 있다.
  browseDir:     ()      => request('POST', '/api/settings/save_dir/browse'),
  addAccounts:   (raw)   => request('POST', '/api/accounts', { raw: raw }),
  removeAccounts:(ids)   => request('DELETE', '/api/accounts', { ids: ids }),
  preview:       (b)     => request('POST', '/api/filename/preview', b),
  thumbUrl:      (jobId, mediaid) => '/api/thumb/' + jobId + '/' + mediaid,
};

/* ---------------------------------------------------------------- DOM */

function $(id) { return document.getElementById(id); }

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function show(node, on) { node.hidden = !on; }

let toastTimer = null;
function toast(message) {
  const box = $('toast');
  box.textContent = message;
  show(box, true);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => show(box, false), 4000);
}

/* data-t / data-t-placeholder / data-t-title 을 현재 언어로 바꾼다.
   키가 없으면 한국어 원문이 그대로 남는다 (i18n.t 와 같은 규칙). */
function applyStaticText() {
  document.querySelectorAll('[data-t]').forEach(n => { n.textContent = t(n.dataset.t); });
  document.querySelectorAll('[data-t-placeholder]').forEach(n => {
    n.placeholder = t(n.dataset.tPlaceholder);
  });
  document.querySelectorAll('[data-t-title]').forEach(n => { n.title = t(n.dataset.tTitle); });
}
