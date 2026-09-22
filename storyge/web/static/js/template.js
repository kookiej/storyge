'use strict';
/* 이름 형식 만들기.
   미리보기는 서버가 그린다 — 선택 구간과 '기존 번호 뒤로 잇기' 규칙을
   여기에 한 번 더 구현하면 두 벌이 금방 어긋난다. */

const TemplateUI = {
  tokens: [],
  timer: null,
  inflight: null,
  onSaved: null,

  init(state) {
    this.tokens = state.tokens || [];

    $('use-template').addEventListener('change', () => {
      this.applyMode();
      this.save();
    });

    const input = $('template-input');
    input.addEventListener('input', () => this.refresh());
    input.addEventListener('change', () => this.save());

    $('template-reset').addEventListener('click', () => {
      input.value = '';
      $('use-template').checked = false;
      this.applyMode();
      this.save();
    });

    this.buildChips();
    this.load(state.config);
  },

  load(cfg) {
    $('use-template').checked = !!cfg.use_filename_template;
    $('template-input').value = cfg.filename_template || '';
    this.applyMode();
  },

  applyMode() {
    const on = $('use-template').checked;
    show($('template-editor'), on);
    show($('template-off-hint'), !on);
    this.refresh();
  },

  /** 묶음마다 칸 하나 — 설명과 그 칩들이 한 덩어리로 묶인다.
      Map 으로 모으므로 목록에서 같은 묶음이 떨어져 있어도 한 칸으로 합쳐진다. */
  buildChips() {
    const box = $('chips');
    box.textContent = '';

    const groups = new Map();
    this.tokens.forEach(spec => {
      if (!groups.has(spec.group)) groups.set(spec.group, []);
      groups.get(spec.group).push(spec);
    });

    groups.forEach((specs, group) => {
      const wrap = el('div', 'chip-group');
      wrap.appendChild(el('span', 'hint', t(group)));

      const row = el('div', 'chip-row');
      specs.forEach(spec => {
        const chip = el('button', 'chip');
        chip.type = 'button';
        chip.appendChild(el('code', null, spec.token));
        // 설명도 한국어 원문이 키다 — 서버가 번역해 주지 않으므로 여기서 칠한다
        chip.appendChild(el('span', 'eg', t(spec.description)));
        chip.addEventListener('click', () => this.insert(spec.token));
        row.appendChild(chip);
      });

      wrap.appendChild(row);
      box.appendChild(wrap);
    });
  },

  /** 언어를 바꿨을 때. 적어 둔 형식과 켜짐/꺼짐은 그대로 두고 글자만 다시 칠한다.
      오류·경고·미리보기는 서버가 그리므로 다시 물어본다 (그 사이 언어가 바뀌어 있다). */
  relang() {
    this.buildChips();
    this.refresh();
  },

  /** 커서 자리에 토큰을 끼워 넣는다. */
  insert(token) {
    const input = $('template-input');
    const start = input.selectionStart === null ? input.value.length : input.selectionStart;
    const end = input.selectionEnd === null ? start : input.selectionEnd;
    input.setRangeText(token, start, end, 'end');
    input.focus();
    this.refresh();
    this.save();
  },

  /** 미리보기를 다시 부른다. 타자마다 부르지 않도록 살짝 미룬다. */
  refresh() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.ask(), 250);
  },

  async ask() {
    if (this.inflight) this.inflight.abort();
    const controller = new AbortController();
    this.inflight = controller;

    const payload = {
      template: $('template-input').value,
      use_template: $('use-template').checked,
      job_id: Grid.jobId || '',
    };

    let data;
    try {
      data = await API.preview(payload);
    } catch (err) {
      if (err.name === 'AbortError') return;
      return;
    } finally {
      if (this.inflight === controller) this.inflight = null;
    }

    const errBox = $('template-err');
    errBox.textContent = (data.errors || []).join(' ');
    show(errBox, (data.errors || []).length > 0);

    const warnBox = $('template-warn');
    warnBox.textContent = (data.warnings || []).join(' ');
    show(warnBox, (data.warnings || []).length > 0);

    const box = $('preview');
    box.textContent = '';
    (data.preview || []).forEach(row => {
      const line = el('div', 'line');
      line.appendChild(el('span', 'who', row.label));
      line.appendChild(el('span', 'name', row.name));
      line.appendChild(el('span', 'ext', row.ext));
      box.appendChild(line);
    });
  },

  async save() {
    try {
      const data = await API.settings({
        use_filename_template: $('use-template').checked,
        filename_template: $('template-input').value,
      });
      if (this.onSaved) this.onSaved(data.config);
    } catch (err) {
      // 형식이 잘못됐을 때는 위의 오류 줄이 이미 알려 준다
      if (!(err.data && err.data.errors && err.data.errors.filename_template)) {
        toast(err.message);
      }
    }
  },
};
