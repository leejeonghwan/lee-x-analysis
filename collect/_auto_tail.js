/* _auto_tail.js — collect_x.js 뒤에 붙어 '한 번 붙여넣으면 끝'으로 만든다.
 * build_auto.py 가 collect_x.js + 이 파일 → collect_auto.js 를 만든다.
 * 직접 쓰는 파일이 아니다. */

(function () {
  const FROM = '2025-06';
  const now = new Date(Date.now() + 9 * 3600000);      // 한국시간
  const TO = now.toISOString().slice(0, 7);
  const NAME = 'posts_' + now.toISOString().slice(0, 10) + '.json';

  // ── 화면에 붙는 진행 표시 ───────────────────────────────────────────────
  const box = document.createElement('div');
  box.style.cssText = [
    'position:fixed', 'right:16px', 'bottom:16px', 'z-index:2147483647',
    'width:300px', 'padding:14px 16px', 'border-radius:12px',
    'background:#11151c', 'color:#e8e6e1', 'font:13px/1.55 -apple-system,BlinkMacSystemFont,sans-serif',
    'box-shadow:0 8px 32px rgba(0,0,0,.45)', 'border:1px solid #2a3240',
  ].join(';');
  box.innerHTML =
    '<div style="font-weight:600;margin-bottom:6px">X 게시물 수집</div>' +
    '<div id="xs" style="color:#9aa4b2">준비 중…</div>' +
    '<div id="xb" style="margin-top:10px"></div>' +
    '<div style="margin-top:8px;color:#6b7580;font-size:11px">이 탭을 앞에 두세요. ' +
    '백그라운드로 보내면 X가 멈춥니다.</div>';
  document.documentElement.appendChild(box);
  const S = box.querySelector('#xs'), BT = box.querySelector('#xb');

  function say(html, color) {
    S.innerHTML = html;
    S.style.color = color || '#9aa4b2';
  }

  function button(label, fn, bg) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = 'width:100%;padding:9px;border:0;border-radius:8px;cursor:pointer;' +
      'font:600 13px -apple-system,sans-serif;background:' + (bg || '#3987e5') + ';color:#fff';
    b.onclick = fn;
    BT.innerHTML = '';
    BT.appendChild(b);
    return b;
  }

  // ── 진행 상황 ───────────────────────────────────────────────────────────
  const total = (() => {
    const [fy, fm] = FROM.split('-').map(Number);
    const [ty, tm] = TO.split('-').map(Number);
    return (ty - fy) * 12 + (tm - fm) + 1;
  })();

  let last = 0, stuck = 0;
  const tick = setInterval(() => {
    const st = window.__X.status();
    const done = total - st.monthsLeft;
    if (st.posts === last) stuck++; else { stuck = 0; last = st.posts; }
    if (st.done || st.monthsLeft === 0) {
      clearInterval(tick);
      say('<b style="color:#58d68d">' + st.posts + '건 수집 완료</b><br>' +
          total + '개월 · 요청 ' + st.requests + '회', '#9aa4b2');
      button('내려받기 (' + st.posts + '건)', () => {
        window.__X.download(NAME);
        say('<b style="color:#58d68d">' + NAME + ' 저장됨</b><br>' +
            '다운로드 폴더를 확인하세요.');
        BT.innerHTML = '';
      }, '#1e8e4a');
      return;
    }
    const pause = st.pauseUntil > Date.now()
      ? ' · <span style="color:#e0a030">제한 대기 ' +
        Math.ceil((st.pauseUntil - Date.now()) / 1000) + '초</span>'
      : '';
    say('<b>' + st.posts + '건</b> 수집 · ' + done + '/' + total + '개월' + pause +
        (stuck > 24 ? '<br><span style="color:#e06060">진행이 멈춘 것 같습니다. ' +
          '탭이 앞에 있는지 확인하세요.</span>' : ''));
  }, 5000);

  // ── 시작 ────────────────────────────────────────────────────────────────
  say('시작합니다 — ' + FROM + ' ~ ' + TO + ' (' + total + '개월)');
  window.collect({ handle: 'Jaemyung_Lee', from: FROM, to: TO }).catch((e) => {
    clearInterval(tick);
    say('<b style="color:#e06060">중단됨</b><br>' + e, '#9aa4b2');
    button('다시 시도', () => location.reload(), '#8a3030');
  });
})();
