'use strict';
/* 화면 전체를 엮는다.
   진행 상황은 0.5초마다 물어본다 (SSE 를 쓰지 않는 이유는 web/jobs.py 참고). */

const POLL_MS = 500;
// 다 찬 막대를 잠깐 보여 주는 시간. 막대의 width 전환이 0.25초라 그보다 넉넉히 둔다.
const PROGRESS_HOLD_MS = 900;

/* ---------------------------------------------------------------- 너비 손잡이 */

const Splitter = {
  KEY: 'storyge.railWidth',
  MIN: 180,      // 더 좁히면 계정 이름이 안 보인다
  MAX: 520,      // 더 넓히면 격자가 한 줄로 줄어든다
  // 계정을 둘 이상 고르면 '전체 선택 / 전체 해제 / N개 삭제' 가 한 줄에 들어가야 한다.
  // app.css 의 var(--rail-w, 300px) 와 같은 값이어야 한다.
  DEFAULT: 300,
  dragging: false,

  init() {
    const bar = $('splitter');
    this.apply(this.remembered());

    bar.addEventListener('pointerdown', ev => {
      ev.preventDefault();
      this.dragging = true;
      bar.classList.add('dragging');
      bar.setPointerCapture(ev.pointerId);
    });
    bar.addEventListener('pointermove', ev => {
      if (!this.dragging) return;
      // 레일은 항상 왼쪽 끝에서 시작하므로 커서의 x 가 곧 너비다
      this.apply(ev.clientX);
    });
    const stop = ev => {
      if (!this.dragging) return;
      this.dragging = false;
      bar.classList.remove('dragging');
      try { bar.releasePointerCapture(ev.pointerId); } catch (ignored) { /* 이미 풀렸다 */ }
      this.remember();
    };
    bar.addEventListener('pointerup', stop);
    bar.addEventListener('pointercancel', stop);
    bar.addEventListener('dblclick', () => { this.apply(this.DEFAULT); this.remember(); });
  },

  apply(px) {
    const width = Math.max(this.MIN, Math.min(this.MAX, Math.round(px)));
    document.documentElement.style.setProperty('--rail-w', width + 'px');
  },

  current() {
    const raw = document.documentElement.style.getPropertyValue('--rail-w');
    return parseInt(raw, 10) || this.DEFAULT;
  },

  // 브라우저 하나의 보기 설정이라 config.json 이 아니라 여기에 둔다.
  // 사생활 보호 창에서는 읽기/쓰기가 예외를 던지므로 전부 감싼다.
  // 이미 너비를 바꿔 본 브라우저는 저장된 값을 그대로 쓴다 — 두 번 누르면 기본값으로 돌아간다.
  remembered() {
    try { return parseInt(localStorage.getItem(this.KEY), 10) || this.DEFAULT; }
    catch (ignored) { return this.DEFAULT; }
  },
  remember() {
    try { localStorage.setItem(this.KEY, String(this.current())); }
    catch (ignored) { /* 저장 못 해도 이번 화면에서는 그대로 쓴다 */ }
  },

  /* --- 접기 ------------------------------------------------------ */

  HIDE_KEY: 'storyge.railHidden',

  initToggle() {
    let off = false;
    try { off = localStorage.getItem(this.HIDE_KEY) === '1'; } catch (ignored) { off = false; }
    this.setHidden(off);
    // 접는 단추는 레일 안(제목 옆), 펴는 단추는 상단바. 어느 쪽을 눌러도 같은 일을 한다.
    $('rail-toggle').addEventListener('click', () => this.setHidden(true));
    $('rail-show').addEventListener('click', () => this.setHidden(false));
  },

  isHidden() { return document.querySelector('.app').classList.contains('rail-off'); },

  setHidden(off) {
    document.querySelector('.app').classList.toggle('rail-off', off);
    $('rail-toggle').setAttribute('aria-pressed', String(off));
    try { localStorage.setItem(this.HIDE_KEY, off ? '1' : ''); }
    catch (ignored) { /* 저장 못 해도 이번 화면에서는 그대로 쓴다 */ }
  },
};

/* ---------------------------------------------------------------- 본체 */

const App = {
  config: {},
  accounts: [],
  picked: new Set(),        // 왼쪽 목록에서 고른 계정 (가져올 범위)
  drag: null,               // 끌어서 고르는 중의 상태
  fetchJob: null,
  saveJob: null,
  busy: false,
  _progressTimer: null,     // 다 찬 막대를 치우려고 걸어 둔 시계

  async boot() {
    applyStaticText();
    Splitter.init();
    Splitter.initToggle();
    this.wire();

    // 새로고침하면 하던 작업을 이어받지 않고 멈춘다. 깨끗한 화면에서 다시 시작한다.
    try { await API.reset(); } catch (ignored) { /* 없으면 없는 대로 진행 */ }

    const state = await API.state();
    this.config = state.config;
    this.accounts = state.accounts;
    this.renderAccounts();
    this.renderConfig();
    TemplateUI.init(state);
    TemplateUI.onSaved = cfg => { this.config = cfg; };
    Grid.onChange = () => this.renderCount();

    // 돌던 작업의 흔적이 남지 않게 못을 박는다
    this.setBusy(false);
    this.progressClear();
    this.renderCount();
  },

  /* ---------------------------------------------------------- 연결 */

  wire() {
    // Enter 와 '추가' 버튼은 목록에 넣기만 하고, Ctrl+Enter 만 바로 가져오기까지 간다.
    $('add-form').addEventListener('submit', ev => {
      ev.preventDefault();
      this.addAccounts({ thenRun: false });
    });
    $('add-go').addEventListener('click', () => this.addAccounts({ thenRun: false }));
    $('add-input').addEventListener('keydown', ev => {
      if (ev.key !== 'Enter' || !(ev.ctrlKey || ev.metaKey)) return;
      // 브라우저에 따라 Ctrl+Enter 가 submit 으로도 새어 나가므로 여기서 막는다
      ev.preventDefault();
      this.addAccounts({ thenRun: true });
    });

    $('add-expand').addEventListener('click', () => this.openAddSheet());
    $('add-text-ok').addEventListener('click', () => this.closeAddSheet(true));
    $('add-text-cancel').addEventListener('click', () => this.closeAddSheet(false));
    $('add-text').addEventListener('keydown', ev => {
      if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) this.closeAddSheet(true);
    });

    $('pick-all').addEventListener('click', () => {
      this.accounts.forEach(a => this.picked.add(a.id));
      this.paintAccounts();
    });
    $('pick-none').addEventListener('click', () => {
      this.picked.clear();
      this.paintAccounts();
    });
    $('bulk-del').addEventListener('click', () => this.removePicked());

    $('run').addEventListener('click', () => this.run());
    $('cancel').addEventListener('click', () => this.cancel());
    $('save').addEventListener('click', () => this.save());

    $('theme-toggle').addEventListener('click', () => this.toggleTheme());
    $('lang-toggle').addEventListener('click', () => this.toggleLang());
    $('settings-open').addEventListener('click', () => $('settings').showModal());

    $('savedir').addEventListener('click', () => $('settings').showModal());
    $('savedir-browse').addEventListener('click', () => this.browseSaveDir());
    $('savedir-open').addEventListener('click', async () => {
      try { await API.openDir(); } catch (err) { toast(err.message); }
    });
    $('confirm-delete').addEventListener('change', async ev => {
      await this.patch({ confirm_delete: ev.target.checked });
    });

    // 끌어서 고르기 — 목록을 다시 그리지 않고 칠하기만 하므로 드래그가 끊기지 않는다
    document.addEventListener('pointermove', ev => this.dragOver(ev));
    document.addEventListener('pointerup', () => { this.drag = null; });
  },

  /* ---------------------------------------------------------- 계정 */

  renderAccounts() {
    const list = $('accounts');
    list.textContent = '';
    this.accounts.forEach(acc => {
      const row = el('li', 'account');
      row.dataset.id = acc.id;

      const del = el('button', 'star del', '✕');
      del.type = 'button';
      del.title = t('삭제');
      del.addEventListener('pointerdown', ev => ev.stopPropagation());
      del.addEventListener('click', async ev => {
        ev.stopPropagation();
        if (this.config.confirm_delete &&
            !confirm(t('@{name} 을(를) 목록에서 지울까요?', { name: acc.id }))) return;
        try {
          const data = await API.removeAccounts([acc.id]);
          this.accounts = data.accounts;
          this.picked.delete(acc.id);
          this.renderAccounts();
        } catch (err) { toast(err.message); }
      });

      row.appendChild(el('span', 'name', '@' + acc.id));
      row.appendChild(del);
      row.addEventListener('pointerdown', ev => this.dragStart(ev, acc.id));
      list.appendChild(row);
    });
    show($('accounts-empty'), this.accounts.length === 0);
    this.paintAccounts();
  },

  /** 고른 표시만 칠한다. 목록을 다시 만들지 않는다. */
  paintAccounts() {
    document.querySelectorAll('.account[data-id]').forEach(row => {
      row.classList.toggle('on', this.picked.has(row.dataset.id));
    });
    // 한 개는 줄마다 있는 ✕ 로 충분하므로, 여럿을 골랐을 때만 일괄 삭제를 보여 준다
    const many = this.picked.size >= 2;
    show($('bulk-del'), many);
    if (many) $('bulk-del').textContent = t('{count}개 삭제', { count: this.picked.size });
  },

  order() { return this.accounts.map(a => a.id); },

  dragStart(ev, id) {
    if (ev.button !== undefined && ev.button !== 0) return;
    ev.preventDefault();
    // 누르기 시작한 줄의 상태를 뒤집는 방향으로 간다 —
    // 그래서 그냥 한 번 누르는 것도 지금까지처럼 토글이 된다.
    this.drag = {
      mode: this.picked.has(id) ? 'off' : 'on',
      anchor: this.order().indexOf(id),
      base: new Set(this.picked),
    };
    this.dragTo(this.drag.anchor);
  },

  dragOver(ev) {
    if (!this.drag) return;
    // elementFromPoint 를 쓰는 이유: 터치에서는 포인터가 처음 줄에 묶여
    // 다른 줄의 pointerover 가 오지 않는다.
    const under = document.elementFromPoint(ev.clientX, ev.clientY);
    const row = under && under.closest ? under.closest('.account[data-id]') : null;
    if (!row) return;
    const index = this.order().indexOf(row.dataset.id);
    if (index >= 0) this.dragTo(index);
  },

  /** 끌기 시작한 줄부터 지금 줄까지에 같은 상태를 입힌다. */
  dragTo(index) {
    const ids = this.order();
    const from = Math.min(this.drag.anchor, index);
    const to = Math.max(this.drag.anchor, index);
    // 끌기 전 상태에서 다시 계산한다 — 되돌아오면 선택도 같이 줄어든다
    this.picked = new Set(this.drag.base);
    for (let i = from; i <= to; i++) {
      if (this.drag.mode === 'on') this.picked.add(ids[i]);
      else this.picked.delete(ids[i]);
    }
    this.paintAccounts();
  },

  async removePicked() {
    const ids = Array.from(this.picked);
    if (ids.length < 2) return;
    if (this.config.confirm_delete &&
        !confirm(t('{count}개를 목록에서 지울까요?', { count: ids.length }))) return;
    try {
      const data = await API.removeAccounts(ids);
      this.accounts = data.accounts;
      this.picked.clear();
      this.renderAccounts();
      toast(t('{count}개를 지웠습니다.', { count: data.removed.length }));
    } catch (err) { toast(err.message); }
  },

  /** 입력칸의 계정을 등록한다. 등록된(또는 이미 있던) 이름 목록을 돌려준다. */
  async addAccounts(opts) {
    const input = $('add-input');
    const raw = input.value.trim();
    if (!raw) return [];
    let data;
    try {
      data = await API.addAccounts(raw);
    } catch (err) {
      toast(err.message);
      return [];
    }
    this.accounts = data.accounts;
    input.value = '';
    this.renderAccounts();

    // 이미 있던 계정을 다시 적었을 때도 가져와야 하므로 둘을 합친다
    const names = data.added.concat(data.existing);
    if (data.added.length) toast(t('추가함: {names}', { names: data.added.join(', ') }));
    else if (data.existing.length) toast(t('이미 있습니다: {names}', { names: data.existing.join(', ') }));

    if (opts && opts.thenRun && names.length) this.run({ accounts: names });
    return names;
  },

  openAddSheet() {
    $('add-text').value = $('add-input').value;
    $('add-sheet').showModal();
    $('add-text').focus();
  },

  closeAddSheet(keep) {
    if (keep) {
      // 줄바꿈이든 여러 칸이든 공백 하나로 합쳐 입력칸에 돌려놓는다
      $('add-input').value = $('add-text').value.split(/\s+/).filter(Boolean).join(' ');
    }
    $('add-sheet').close();
    if (keep) $('add-input').focus();
  },

  /* ---------------------------------------------------------- 설정 */

  renderConfig() {
    const cfg = this.config;
    $('savedir-input').value = cfg.save_dir || '';
    $('confirm-delete').checked = !!cfg.confirm_delete;
    $('lang-toggle').textContent = window.LANG === 'en' ? 'KR' : 'EN';
    $('theme-toggle').textContent = cfg.theme === 'light' ? '☀' : '☾';

    $('savedir').textContent = cfg.save_dir || t('저장 폴더를 정해 주세요');
    $('savedir').classList.toggle('danger-link', !cfg.save_dir_ok);
    // 수집 방식은 화면에서 고르지 않는다 — 막힌 사이트는 서버가 알아서 건너뛴다.
  },

  async patch(body) {
    try {
      const data = await API.settings(body);
      this.config = data.config;
      this.renderConfig();
      return data;
    } catch (err) {
      toast(err.message);
      return null;
    }
  },

  async applySaveDir() {
    const errBox = $('savedir-err');
    const data = await this.patch({ save_dir: $('savedir-input').value });
    if (data) {
      show(errBox, false);
      toast(t('저장 폴더를 바꿨습니다.'));
      return true;
    }
    errBox.textContent = t('그 폴더를 쓸 수 없습니다.');
    show(errBox, true);
    return false;
  },

  /** 서버 PC 에 탐색기 창을 띄워 폴더를 고른다. */
  async browseSaveDir() {
    const button = $('savedir-browse');
    button.disabled = true;
    toast(t('폴더 선택 창을 띄웠습니다. 다른 창 뒤에 있을 수 있습니다.'));
    try {
      const data = await API.browseDir();
      if (data.cancelled) return false;
      if (!data.ok) { toast(data.error || t('그 폴더를 쓸 수 없습니다.')); return false; }
      $('savedir-input').value = data.resolved;
      return await this.applySaveDir();
    } catch (err) {
      toast(err.message);
      return false;
    } finally {
      button.disabled = false;
    }
  },

  /** 저장 폴더가 없으면 설정을 열고 곧바로 고르게 한다. */
  async ensureSaveDir() {
    if (this.config.save_dir_ok) return true;
    if (!$('settings').open) $('settings').showModal();
    return await this.browseSaveDir();
  },

  async toggleTheme() {
    const next = this.config.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    await this.patch({ theme: next });
  },

  async toggleLang() {
    const next = window.LANG === 'en' ? 'ko' : 'en';
    const data = await this.patch({ lang: next });
    // 저장에 실패하면 언어도 화면도 건드리지 않는다 (patch 가 이미 알려 줬다)
    if (data) this.relang(data.config.lang);
  },

  /** 언어만 갈아 끼운다. **새로고침하지 않는다** — 새로고침하면 /api/reset 이
      돌던 수집을 멈추고 격자와 고른 것이 전부 날아간다. 대응표(window.I18N)는
      언어와 상관없이 늘 실려 오므로 그 자리에서 다시 칠하기만 하면 된다. */
  relang(lang) {
    window.LANG = lang;
    document.documentElement.lang = lang;
    applyStaticText();
    this.renderAccounts();     // 줄마다의 '삭제' 도움말 (고른 계정은 그대로 남는다)
    this.renderConfig();       // 저장 폴더 안내와 EN/KR 표시
    this.renderCount();
    Grid.relang();
    TemplateUI.relang();
    // 진행 줄은 다음 폴링이(0.5초) 새 언어로 다시 쓴다.
    // 안내 줄(#notes)은 서버가 가져올 때 그 언어로 만들어 둔 문장이라 그대로 남는다.
  },

  /* ---------------------------------------------------------- 가져오기 */

  targets() {
    if (this.picked.size) return Array.from(this.picked);
    return null;                // null = 서버가 등록된 계정 전체로 정한다
  },

  setBusy(on) {
    this.busy = on;
    $('run').hidden = on;
    show($('cancel'), on);
    if (on) {
      // 도는 동안에는 막대와 도는 표시를 계속 보여 준다
      clearTimeout(this._progressTimer);
      show($('progress'), true);
      show($('progress-track'), true);
      show($('spinner'), true);
    }
    // 끝났을 때 진행 줄을 어떻게 할지는 부르는 쪽이 정한다
    // (잘 끝났으면 progressFinish, 중간에 엎어졌으면 progressClear).
    $('save').disabled = on || Grid.selected.size === 0;
  },

  /** 진행 줄을 통째로 치운다. 남겨 두면 저장 단계에서 줄을 다시 열 때
      **지난 번 막대와 스피너가 되살아나** 아직 도는 것처럼 보인다. */
  progressClear() {
    clearTimeout(this._progressTimer);
    this._progressTimer = null;
    show($('progress'), false);
    this.progressIdle();
  },

  progressIdle() {
    show($('spinner'), false);
    show($('progress-track'), false);
    $('progress-fill').style.width = '0%';
    $('progress-text').textContent = '';
  },

  /** 잘 끝났을 때. **막대를 끝까지 채워 보여 준 뒤** 치운다.
      바로 숨기면 막대가 다 차는 것을 볼 수 없어 하다 만 것처럼 보인다. */
  progressFinish() {
    clearTimeout(this._progressTimer);
    show($('progress'), true);
    show($('progress-track'), true);
    show($('spinner'), false);
    $('progress-fill').style.width = '100%';
    // 끝났으면 '3/3 계정' 처럼 세는 말 대신 끝났다고 말한다 (가져오기·저장 모두).
    $('progress-text').textContent = t('완료');
    this._progressTimer = setTimeout(() => this.progressClear(), PROGRESS_HOLD_MS);
  },

  async run(opts) {
    if (this.busy) return;
    const wanted = (opts && opts.accounts) || this.targets();
    if (!wanted && !this.accounts.length) { toast(t('계정을 먼저 추가해 주세요.')); return; }
    if (!await this.ensureSaveDir()) return;

    try {
      const started = await API.fetchStart({
        accounts: wanted,
        skip_downloaded: true,
      });
      this.fetchJob = started.job_id;
      Grid.reset(this.fetchJob);
      Grid.setLoading(true);
      $('notes').textContent = '';
      show($('notes'), false);
      this.setProgress(0, started.accounts.length, null);
      this.setBusy(true);
      this.pollFetch();
    } catch (err) {
      if (err.status === 409 && err.data.job_id) {
        this.fetchJob = err.data.job_id;
        this.setBusy(true);
        this.pollFetch();
      } else {
        toast(err.message);
      }
    }
  },

  async cancel() {
    if (!this.fetchJob) return;
    try { await API.fetchCancel(this.fetchJob); } catch (err) { toast(err.message); }
  },

  async pollFetch() {
    let data;
    try {
      data = await API.fetchState(this.fetchJob);
    } catch (err) {
      this.setBusy(false);
      this.progressClear();
      toast(err.message);
      return;
    }

    Grid.sync(data.items || []);
    this.setProgress(data.done, data.total, data.current_account);
    this.renderNotes(data.notes);

    if (data.state === 'running') {
      setTimeout(() => this.pollFetch(), POLL_MS);
      return;
    }

    Grid.setLoading(false);
    this.setBusy(false);
    // 끝까지 간 것만 막대를 채워 보여 준다. 중간에 엎어진 것을 100% 로 보여 주면 거짓말이다.
    if (data.state === 'done') this.progressFinish();
    else this.progressClear();

    if (data.state === 'error') toast(t('가져오다 문제가 생겼습니다: {reason}', { reason: data.error || '?' }));
    else if (data.state === 'cancelled') toast(t('중지했습니다.'));
    // 사이트를 다 해 보고도 못 가져온 것과 정말 올라온 게 없는 것은 다른 일이다.
    // 둘을 같은 문구로 알리면 막힌 것을 알아챌 수 없다.
    else if (data.blocked) toast(t('서버에 연결하지 못했습니다.'));
    else if (!Grid.items.size) toast(t('새로 저장할 스토리가 없습니다.'));
  },

  setProgress(done, total, current) {
    const ratio = total ? Math.round((done / total) * 100) : 0;
    show($('progress-track'), true);
    $('progress-fill').style.width = ratio + '%';
    $('progress-text').textContent = current
      ? t('@{account} 확인 중 ({done}/{total})', { account: current, done: done + 1, total: total })
      : t('{done}/{total} 계정', { done: done, total: total });
    // 막대는 **끝난 계정만** 채운다 (부풀리지 않는다). 계정 하나를 보는 동안에는
    // 막대가 멈춰 보이므로, 그동안 일하고 있다는 것은 도는 표시가 맡는다.
    show($('spinner'), this.busy);
  },

  renderNotes(notes) {
    const box = $('notes');
    box.textContent = '';
    (notes || []).forEach(note => box.appendChild(el('li', null, note)));
    show(box, (notes || []).length > 0);
  },

  renderCount() {
    const count = Grid.selected.size;
    $('count').textContent = t('{count}개 선택', { count: count });
    $('save').disabled = this.busy || count === 0;
  },

  /* ---------------------------------------------------------- 저장 */

  async save() {
    const mediaids = Grid.chosen();
    if (!mediaids.length) return;
    if (!await this.ensureSaveDir()) return;
    try {
      const started = await API.saveStart({ job_id: this.fetchJob, mediaids: mediaids });
      this.saveJob = started.job_id;
      $('save').disabled = true;
      this.pollSave();
    } catch (err) { toast(err.message); }
  },

  async pollSave() {
    let data;
    try {
      data = await API.saveState(this.saveJob);
    } catch (err) {
      this.progressClear();
      toast(err.message);
      return;
    }

    // 저장은 몇 개 중 몇 개인지 정확히 아니까 막대로 보여 준다.
    // (가져오기가 남겨 둔 값을 물려받지 않도록 여기서 직접 정한다.)
    clearTimeout(this._progressTimer);
    show($('progress'), true);
    show($('progress-track'), true);
    show($('spinner'), false);
    $('progress-fill').style.width =
      (data.total ? Math.round((data.done / data.total) * 100) : 0) + '%';
    $('progress-text').textContent =
      t('{done}/{total} 저장 중', { done: data.done, total: data.total });

    if (data.state === 'running') {
      setTimeout(() => this.pollSave(), POLL_MS);
      return;
    }

    // 가져오기와 같은 규칙 — 끝까지 간 것만 막대를 채워 보여 준다
    if (data.state === 'done') this.progressFinish();
    else this.progressClear();

    this.renderCount();
    if (data.state === 'error') {
      toast(t('저장하다 문제가 생겼습니다: {reason}', { reason: data.error || '?' }));
      return;
    }
    toast(t('{ok}개 저장, {existed}개 건너뜀, {failed}개 실패',
            { ok: data.ok, existed: data.existed, failed: data.failed }));
    const failed = (data.results || []).filter(r => r.status === 'failed');
    this.renderNotes(failed.map(r => t('{name}: {reason}', { name: r.name, reason: r.reason })));
  },
};

App.boot().catch(err => {
  document.body.textContent = 'Storyge: ' + err.message;
});
