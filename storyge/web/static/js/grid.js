'use strict';
/* 썸네일 격자.
   고른 것은 mediaid 문자열의 Set 으로 들고 있다 — DOM 순서와 무관하므로,
   가져오는 도중에 칸이 덧붙어도 선택이 흐트러지지 않는다.
   (데스크톱 picker.py 가 self.selected 를 mediaid 로 키잉하는 것과 같은 이유) */

const Grid = {
  jobId: null,
  order: [],                 // 화면에 그려진 순서 (shift 범위 선택용)
  items: new Map(),          // mediaid -> item
  selected: new Set(),
  // 가져오는 중인가. 칸을 미리 그려 두지는 않고(빈 화면으로 둔다),
  // '가져오기를 누르면 나옵니다' 안내만 내보내지 않으려고 쓴다.
  loading: false,
  lastClicked: null,
  onChange: null,

  reset(jobId) {
    this.jobId = jobId;
    this.items.clear();
    this.selected.clear();
    this.order = [];
    this.lastClicked = null;
    this.render();
  },

  /** 서버에서 온 목록을 반영한다. 이미 있는 것은 건드리지 않는다. */
  sync(list) {
    let fresh = false;
    list.forEach(item => {
      if (!this.items.has(item.mediaid)) {
        this.items.set(item.mediaid, item);
        fresh = true;
      }
    });
    if (fresh) this.render();
    return fresh;
  },

  setLoading(on) {
    if (this.loading === on) return;
    this.loading = on;
    this.render();
  },

  /* --- 선택 ------------------------------------------------------ */

  toggle(mediaid, rangeTo) {
    if (rangeTo && this.lastClicked) {
      const from = this.order.indexOf(this.lastClicked);
      const to = this.order.indexOf(mediaid);
      if (from >= 0 && to >= 0) {
        const on = !this.selected.has(mediaid);
        const [lo, hi] = from < to ? [from, to] : [to, from];
        for (let i = lo; i <= hi; i++) {
          if (on) this.selected.add(this.order[i]);
          else this.selected.delete(this.order[i]);
        }
        this.lastClicked = mediaid;
        this.paint();
        return;
      }
    }
    if (this.selected.has(mediaid)) this.selected.delete(mediaid);
    else this.selected.add(mediaid);
    this.lastClicked = mediaid;
    this.paint();
  },

  setAll(on) {
    if (on) this.items.forEach((_, key) => this.selected.add(key));
    else this.selected.clear();
    this.paint();
  },

  setAccount(account, on) {
    this.items.forEach((item, key) => {
      if (item.account !== account) return;
      if (on) this.selected.add(key);
      else this.selected.delete(key);
    });
    this.paint();
  },

  chosen() { return Array.from(this.selected); },

  /* --- 그리기 ---------------------------------------------------- */

  /** 선택 표시만 다시 칠한다 (이미지를 다시 받지 않는다). */
  paint() {
    document.querySelectorAll('.cell[data-id]').forEach(node => {
      node.classList.toggle('on', this.selected.has(node.dataset.id));
    });
    document.querySelectorAll('.section-head input').forEach(box => {
      const account = box.dataset.account;
      const all = Array.from(this.items.values()).filter(i => i.account === account);
      const picked = all.filter(i => this.selected.has(i.mediaid)).length;
      box.checked = picked > 0 && picked === all.length;
      box.indeterminate = picked > 0 && picked < all.length;
    });
    if (this.onChange) this.onChange();
  },

  /** 격자를 통째로 다시 만든다.
      계정별로 묶어 그리므로 뒤에 덧붙이면 한 계정이 두 구획으로 쪼개진다
      (picker._add_items 가 전체를 다시 그리는 것과 같은 이유). */
  render() {
    const root = $('grid');
    root.textContent = '';
    this.order = [];

    const groups = new Map();
    this.items.forEach(item => {
      if (!groups.has(item.account)) groups.set(item.account, []);
      groups.get(item.account).push(item);
    });

    groups.forEach((list, account) => {
      list.sort((a, b) => a.taken_at.localeCompare(b.taken_at));
      root.appendChild(this.sectionHead(account, list.length));
      const box = el('div', 'grid');
      list.forEach(item => {
        this.order.push(item.mediaid);
        box.appendChild(this.cell(item));
      });
      root.appendChild(box);
    });

    // 가져오는 동안에는 빈 화면으로 둔다 — 미리 그린 빈 칸은 몇 개가 올지도 모르면서
    // 아는 척을 하게 되고, 진행은 위쪽 막대가 이미 말해 준다.
    // 다만 안내 문구('가져오기를 누르면...')는 그때 내보내지 않는다.
    show($('empty'), this.items.size === 0 && !this.loading);
    this.paint();
  },

  /** 언어만 바꿔 다시 칠한다.
      칸을 다시 만들지 않으므로 썸네일을 다시 받지 않고 스크롤 자리도 그대로다
      (고른 것은 어차피 this.selected 에 있어 다시 그려도 남지만, 격자를 통째로
      갈아 끼우면 화면이 한 번 깜빡이고 보고 있던 자리를 잃는다). */
  relang() {
    document.querySelectorAll('.section-head').forEach(head => {
      head.querySelector('.howmany').textContent =
        t('{count}개', { count: head.dataset.count });
    });
    document.querySelectorAll('.cell .guess').forEach(mark => {
      mark.title = t('원본 시각을 알 수 없어 추정한 시각입니다.');
    });
    // 이미지를 못 받아 회색으로 남은 칸
    document.querySelectorAll('.cell .fail').forEach(node => {
      node.textContent = t('미리보기 실패');
    });
  },

  sectionHead(account, count) {
    const head = el('div', 'section-head');
    head.dataset.count = count;          // 언어를 바꿀 때 세는 말을 다시 쓰려고 들고 있는다
    const box = el('input');
    box.type = 'checkbox';
    box.dataset.account = account;
    box.addEventListener('change', () => this.setAccount(account, box.checked));
    head.appendChild(box);
    head.appendChild(el('span', 'who', '@' + account));
    head.appendChild(el('span', 'howmany', t('{count}개', { count: count })));
    return head;
  },

  cell(item) {
    const cell = el('div', 'cell');
    cell.dataset.id = item.mediaid;

    const frame = el('div', 'frame');
    const img = el('img');
    img.loading = 'lazy';
    img.alt = '';
    img.src = API.thumbUrl(this.jobId, item.mediaid);
    img.addEventListener('error', () => {
      frame.textContent = '';
      frame.appendChild(el('div', 'fail', t('미리보기 실패')));
    });
    frame.appendChild(img);
    if (item.is_video) frame.appendChild(el('span', 'tag', '▶'));
    cell.appendChild(frame);

    const caption = el('div', 'caption');
    if (item.time_basis !== 'exact') {
      const mark = el('span', 'guess', '~');
      mark.title = t('원본 시각을 알 수 없어 추정한 시각입니다.');
      caption.appendChild(mark);
    }
    caption.appendChild(el('span', null, item.label));
    // 어느 사이트에서 왔는지는 보여 주지 않는다 — 사용자가 고르지 않는 것이다.
    cell.appendChild(caption);

    cell.addEventListener('click', ev => this.toggle(item.mediaid, ev.shiftKey));
    return cell;
  },
};
