/* collect_auto.js — 생성된 파일입니다. 고치지 마십시오.
 * 원본: collect/collect_x.js + collect/_auto_tail.js
 * 생성: build_auto.py (2026-10-15)
 *
 * 쓰는 법
 *   1. 로그인한 상태로 X 검색 결과 페이지를 연다
 *      https://x.com/search?q=(from%3AJaemyung_Lee)&f=live
 *   2. 개발자도구 콘솔(Option+Cmd+J)에 이 파일 전체를 붙여넣고 Enter
 *   3. 오른쪽 아래 상자가 알아서 진행된다. 끝나면 '내려받기'를 누른다
 *
 *   수집 범위는 2025-06 부터 '오늘이 속한 달'까지 자동으로 잡는다.
 *   탭을 앞에 둬야 한다 — 백그라운드로 가면 X 가 응답을 멈춘다.
 */

/*
 * collect_x.js — X 계정의 게시물을 월 단위로 전수 수집한다.
 *
 * 사용법
 *   1. 로그인한 상태에서 아무 X 검색 결과 페이지를 연다.
 *      예: https://x.com/search?q=(from%3AJaemyung_Lee)&f=live
 *      (검색 결과 페이지여야 한다 — '인기 / 최신' 탭이 있어야 동작한다)
 *   2. 개발자도구 콘솔에 이 파일 전체를 붙여넣는다.
 *   3. collect({ handle: 'Jaemyung_Lee', from: '2025-07', to: '2026-09' })
 *   4. 진행 상황은 __X.status() 로 확인한다.
 *   5. 끝나면 __X.download() 로 JSON 파일을 내려받는다.
 *
 * 왜 이렇게 하나
 *   SearchTimeline 엔드포인트는 x-client-transaction-id 헤더를 요구한다.
 *   이 값은 웹 클라이언트가 난독화된 코드로 매 요청마다 새로 만들고 재사용되지 않는다.
 *   그래서 헤더를 위조하는 대신, 웹 클라이언트가 스스로 만든 요청의 URL을
 *   보내기 직전에 바꿔치기한다. 인증과 서명은 클라이언트가 알아서 한다.
 *
 * 주의
 *   - 검색 API는 15분당 50건 제한이 있다. 429를 만나면 자동으로 쉰다.
 *   - 리트윗은 X 검색이 반환하지 않으므로 결과에 포함되지 않는다.
 *   - 본인 계정 세션으로 읽기만 한다. 아무것도 쓰지 않는다.
 *
 * 저장되는 필드
 *   t_iso  작성 시각 (한국시간)        fav/rt/rep  좋아요·리트윗·답글 수
 *   x      본문 (긴 글은 note_tweet)   rp/q        답글 여부 / 인용 여부
 *   u      본문 링크의 원래 주소 배열 (t.co 를 펼친 expanded_url)
 *   md     첨부 미디어 종류 배열 (photo / video / animated_gif)
 *   qid    인용한 원글의 ID (인용이 아니면 null)
 */

(function () {
  const X = (window.__X = {});

  // ── 1. 웹 클라이언트 번들에서 queryId 와 feature 스위치를 꺼낸다 ──────────
  X.init = async function () {
    const main = [...document.querySelectorAll('script[src]')]
      .map((s) => s.src)
      .find((u) => u.includes('/client-web/main.'));
    if (!main) throw new Error('main bundle not found — X 검색 페이지에서 실행하세요');

    const src = await (await fetch(main)).text();
    const at = src.indexOf('operationName:"SearchTimeline"');
    if (at < 0) throw new Error('SearchTimeline not found in bundle');

    const qid = (src.slice(at - 200, at).match(/queryId:"([^"]+)"\s*,\s*$/) || [])[1];
    const fs = (src.slice(at, at + 4000).match(/featureSwitches:\[([^\]]*)\]/) || [])[1];
    const feat = Object.fromEntries(
      (fs ? fs.split(',').map((s) => s.replace(/"/g, '')) : []).map((k) => [k, true])
    );
    X.qid = qid;
    X.feat = feat;
    return { qid, features: Object.keys(feat).length };
  };

  X.url = function (query, cursor) {
    const vars = { rawQuery: query, count: 20, querySource: 'typed_query', product: 'Latest' };
    if (cursor) vars.cursor = cursor;
    return (
      `https://x.com/i/api/graphql/${X.qid}/SearchTimeline` +
      `?variables=${encodeURIComponent(JSON.stringify(vars))}` +
      `&features=${encodeURIComponent(JSON.stringify(X.feat))}`
    );
  };

  // ── 2. 웹 클라이언트의 XHR 을 가로채 URL 만 바꾼다 ────────────────────────
  X.queue = [];
  X.inbox = [];
  if (!X.hooked) {
    const open = XMLHttpRequest.prototype.open;
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
      this.__url = '' + url;
      if (('' + url).includes('SearchTimeline') && X.queue.length) {
        const job = X.queue.shift();
        this.__job = job;
        arguments[1] = job.url;
        this.__url = job.url;
      }
      return open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
      const self = this;
      if (self.__job) {
        self.addEventListener('load', function () {
          X.inbox.push({ job: self.__job, status: self.status, body: self.responseText });
        });
      }
      return send.apply(this, arguments);
    };
    X.hooked = true;
  }

  // 탭을 두 번 눌러 클라이언트가 SearchTimeline 요청을 한 번 내도록 유도한다
  X.pump = async function (wait) {
    wait = wait || 900;
    const tabs = [...document.querySelectorAll('a[role="tab"], div[role="tab"]')];
    const top = tabs[0], latest = tabs[1];
    if (!top || !latest) throw new Error('검색 결과 페이지가 아닙니다');
    top.click();
    await new Promise((r) => setTimeout(r, wait));
    latest.click();
    await new Promise((r) => setTimeout(r, wait));
  };

  // ── 3. 응답에서 게시물을 긁어낸다 ────────────────────────────────────────
  function walk(obj, visit) {
    const seen = new Set();
    (function rec(x) {
      if (!x || typeof x !== 'object' || seen.has(x)) return;
      seen.add(x);
      if (Array.isArray(x)) return x.forEach(rec);
      visit(x);
      for (const k in x) rec(x[k]);
    })(obj);
  }

  X.posts = {};
  X.months = {};
  X.state = { requests: 0, rateLimited: 0, pauseUntil: 0, stop: false, done: false };

  function drain(handle) {
    X.inbox.splice(0).forEach((res) => {
      const st = X.months[res.job.key];
      if (!st) return;
      if (res.status === 429) {
        X.state.rateLimited++;
        X.state.pauseUntil = Date.now() + 65000;
        return;
      }
      if (res.status !== 200) {
        st.tries = (st.tries || 0) + 1;
        if (st.tries > 5) st.done = true;
        return;
      }
      let json;
      try { json = JSON.parse(res.body); } catch (e) { return; }

      let next = null, found = 0;
      walk(json, (node) => {
        if (node.cursorType === 'Bottom' && node.value) next = node.value;
        if (node.__typename === 'Tweet' && node.legacy && node.legacy.created_at && node.rest_id) {
          const user =
            node.core?.user_results?.result?.core?.screen_name || null;
          if (!user || user.toLowerCase() !== handle.toLowerCase()) return;
          const note = node.note_tweet?.note_tweet_results?.result;
          // 본문의 링크는 t.co 로 단축돼 있어 도메인을 알 수 없다. 원래 주소는
          // entities.urls[].expanded_url 에 들어 있고, 긴 글(note_tweet)은
          // 자기 entity_set 에 따로 들고 있다. 첨부 사진·동영상은 링크가 아니라
          // media 로 오므로 종류만 센다.
          const le = node.legacy.entities || {};
          const ne = (note && note.entity_set) || {};
          const urls = [...(le.urls || []), ...(ne.urls || [])]
            .map((u) => u.expanded_url || u.url)
            .filter(Boolean);
          const media = [
            ...((node.legacy.extended_entities || {}).media || []),
            ...(le.media || []),
          ];
          X.posts[node.rest_id] = {
            t_iso: new Date(new Date(node.legacy.created_at).getTime() + 9 * 3600000).toISOString(),
            x: (note && note.text) || node.legacy.full_text || '',
            fav: node.legacy.favorite_count,
            rt: node.legacy.retweet_count,
            rep: node.legacy.reply_count,
            rp: !!node.legacy.in_reply_to_status_id_str,
            q: !!node.legacy.is_quote_status,
            u: [...new Set(urls)],
            md: [...new Set(media.map((m) => m.type).filter(Boolean))],
            qid: node.legacy.quoted_status_id_str || null,
          };
          found++;
        }
      });
      st.pages++;
      if (found === 0 || !next) st.done = true;
      else st.cursor = next;
    });
  }

  // ── 4. 월 단위로 돌린다 ─────────────────────────────────────────────────
  X.collect = async function (opts) {
    const handle = opts.handle;
    const [fy, fm] = opts.from.split('-').map(Number);
    const [ty, tm] = opts.to.split('-').map(Number);

    let y = fy, m = fm;
    while (y < ty || (y === ty && m <= tm)) {
      const key = `${y}-${String(m).padStart(2, '0')}`;
      let ny = y, nm = m + 1;
      if (nm > 12) { nm = 1; ny++; }
      X.months[key] = {
        query: `(from:${handle}) since:${key}-01 until:${ny}-${String(nm).padStart(2, '0')}-01`,
        cursor: null, done: false, pages: 0,
      };
      m++; if (m > 12) { m = 1; y++; }
    }

    await X.init();
    X.state.stop = false;
    X.state.done = false;

    while (!X.state.stop) {
      try {
        if (Date.now() < X.state.pauseUntil) {
          await new Promise((r) => setTimeout(r, 5000));
          continue;
        }
        // 한 사이클에 최대 2건 — '인기'와 '최신' 클릭이 각각 요청 하나를 낸다
        const jobs = [];
        for (const key of Object.keys(X.months)) {
          const st = X.months[key];
          if (st.done || X.queue.some((j) => j.key === key)) continue;
          jobs.push({ key, url: X.url(st.query, st.cursor) });
          if (jobs.length >= 2) break;
        }
        if (!jobs.length) { X.state.done = true; break; }

        jobs.forEach((j) => X.queue.push(j));
        await X.pump();
        X.state.requests++;
        drain(handle);
        X.queue.length = 0;
      } catch (e) {
        X.state.error = '' + e;
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
    return X.status();
  };

  X.status = function () {
    const left = Object.values(X.months).filter((m) => !m.done).length;
    return {
      posts: Object.keys(X.posts).length,
      requests: X.state.requests,
      monthsLeft: left,
      rateLimited: X.state.rateLimited,
      pauseUntil: X.state.pauseUntil,
      done: X.state.done,
    };
  };

  X.download = function (name) {
    const blob = new Blob([JSON.stringify(X.posts)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name || 'posts_full.json';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
    return Object.keys(X.posts).length;
  };

  window.collect = X.collect;
  console.log('준비됨. collect({ handle: "Jaemyung_Lee", from: "2025-07", to: "2026-09" })');
})();


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

