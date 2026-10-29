"""update.py — 새 게시물을 고정된 지도 안으로 넣고, 결과물 전체를 다시 만든다.

    python3 update.py --add ~/Downloads/posts_new.json   # 합치고 전부 다시 만들기
    python3 update.py                                    # 다시 만들기만
    python3 update.py --add new.json --check             # 무엇이 바뀌는지만 보기

무엇이 바뀌고 무엇이 안 바뀌나
    기본 동작은 지도를 **매번 새로 적합**하는 것이다. 좌표는 움직인다. 그게
    맞다 — 새 글이 들어오면 지형도 달라져야 한다. 대신 두 가지를 붙들어 둔다.

    1. **군집 정체성.** k-means 를 예전 중심에서 출발시킨다(warm start).
       군집 6 은 지난달에도 다음 달에도 '치안·민생 단속'이다. 손으로 붙인
       이름, 색 팔레트, 월별 추이 그래프가 그대로 맞는다. 찬 상태로 다시
       적합하면 번호가 뒤바뀌어 매달 이름을 다시 붙여야 한다.
    2. **방향.** t-SNE 는 회전과 반사를 임의로 정한다. 겹치는 글들을 기준으로
       예전 지도에 맞춰 돌려 놓는다(프로크루스테스). 지도가 뒤집히지 않는다.

    매 실행마다 라벨 유지율과 '겹치는 글이 움직인 거리'를 보고한다. 유지율이
    90% 아래로 떨어지면 군집 이름이 아직 맞는지 사람이 확인할 때다.

--freeze
    좌표를 아예 고정하고 싶을 때. 기사를 막 발행해 캡처와 어긋나면 안 되는
    동안 쓴다. 군집은 가장 가까운 중심으로 정하고, 좌표는 임베딩이 비슷한
    기준점 12개의 가중평균 자리에 놓는다. 오차는 validate_projection.py 참조.
"""
import json, re, html, os, sys, csv, hashlib, argparse
import numpy as np
from collections import Counter, defaultdict

B = os.path.dirname(os.path.abspath(__file__))
HANDLE = 'Jaemyung_Lee'
# 원자료로 들고 있는 구간. X 검색이 since/until 을 벗어난 옛 글을 가끔
# 흘려보내는데(고정된 글이나 다시 떠오른 글로 보인다), 그게 섞이면 월별
# 집계에 없는 달이 생기고 과거 구간 경계가 어긋난다. 합칠 때 걸러낸다.
RAW_FROM = '2025-06'
SELF = ('x.com', 'twitter.com', 't.co', 'mobile.twitter.com')
VIDEO = ('youtube.com', 'youtu.be', 'm.youtube.com')

URL = re.compile(r'https?://\S+')
MENT = re.compile(r'@\w+')
FOOT = re.compile(r'[-–]\s*이재명 후원회.*', re.S)
STOP = set('''있습니다 합니다 하겠습니다 드립니다 그리고 하지만 여러분 대한민국 국민 우리 오늘 지금
대통령 것입니다 위해 통해 함께 모든 더욱 정부 감사합니다 있는 있도록 하는 해서 대한 이번 관련 대해
만들 만들겠습니다 하고 해야 위한 되는 됩니다 같은 같이 다시 계속 매우 정말 많은 많이 그런 이런 저런
무엇 어떤 라며 라고 이라 에서 으로 에게 까지 부터 보다 처럼 이라고'''.split())


def clean(raw_text):
    t = html.unescape(raw_text)
    t = FOOT.sub('', t)
    t = URL.sub(' ', t)
    t = MENT.sub(' ', t)
    t = re.sub(r'[<>]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def toks(t):
    return [w for w in re.findall(r'[가-힣]{2,8}|[A-Za-z]{3,}', t) if w not in STOP]


# ── 1. 합치기 ────────────────────────────────────────────────────────────
def merge(path):
    full = json.load(open(f'{B}/posts_full.json'))
    new = json.load(open(path))
    if not isinstance(new, dict):
        raise SystemExit('수집 파일은 {게시물ID: {...}} 모양이어야 합니다')
    added, touched, months, old_posts = 0, 0, Counter(), []
    for pid, d in new.items():
        if not re.fullmatch(r'\d{15,25}', str(pid)):
            raise SystemExit(f'게시물 ID가 이상합니다: {pid!r} — 자리수가 잘렸을 수 있습니다')
        if d['t_iso'][:7] < RAW_FROM:
            if pid not in full:
                old_posts.append(d['t_iso'][:10])
            continue
        if pid in full:
            if full[pid] != d:
                touched += 1
            full[pid] = d           # 좋아요 수 등 지표는 새 값으로 덮는다
        else:
            added += 1
            months[d['t_iso'][:7]] += 1
            full[pid] = d
    print(f'합치기: 새 게시물 {added}건, 지표 갱신 {touched}건, 전체 {len(full)}건')
    if old_posts:
        print(f'  {RAW_FROM} 이전 글 {len(old_posts)}건은 건너뜁니다 '
              f'({", ".join(sorted(old_posts)[:4])}) — 검색이 흘린 옛 글입니다')
    if months:
        print('  새 글이 들어온 달:', ', '.join(f'{m} {n}건' for m, n in sorted(months.items())))
    return full, added


# ── 2. 본문 정리와 임베딩 ────────────────────────────────────────────────
def prepare(full, meta, anc, stored=False):
    """게시물을 정리해 시간순으로 세우고, 임베딩을 채운다.

    stored=True 면 이미 모델에 있는 글은 저장해 둔 벡터를 쓰고 새 글만
    임베딩한다(--freeze 용). 기본은 전부 다시 임베딩한다 — 저장본은 float16
    이라 미세하게 반올림돼 있고, t-SNE 는 그 정도 차이에도 다른 국소해로
    빠지기 때문이다. 1,000건이면 몇 초면 끝난다."""
    rows = []
    for pid, d in full.items():
        t = clean(d['x'])
        if len(t) < 8:
            continue
        rows.append(dict(id=pid, ts=d['t_iso'], month=d['t_iso'][:7], day=d['t_iso'][:10],
                         text=t, fav=d.get('fav', 0), rp=bool(d.get('rp')), q=bool(d.get('q')),
                         u=d.get('u'), md=d.get('md') or []))
    rows.sort(key=lambda r: r['ts'])
    dropped = len(full) - len(rows)

    have = {str(i): k for k, i in enumerate(anc['ids'])}
    A_vec = anc['vec'].astype(np.float32)
    for r in rows:
        r['new'] = r['id'] not in have
    n_new = sum(r['new'] for r in rows)

    todo = [i for i, r in enumerate(rows) if r['new'] or not stored]
    V = np.zeros((len(rows), A_vec.shape[1]), dtype=np.float32)
    for i, r in enumerate(rows):
        if not r['new'] and stored:
            V[i] = A_vec[have[r['id']]]
    if todo:
        from model2vec import StaticModel
        W = StaticModel.from_pretrained(meta['embed_model']).encode([rows[i]['text'] for i in todo])
        V[todo] = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-9)
    return rows, V, dropped, n_new


# ── 2a. 기본: 지도를 다시 적합한다 (군집 정체성은 유지) ──────────────────
def refit(rows, V, meta, anc):
    """좌표는 새로 적합하고, 군집 번호·이름·색은 그대로 유지한다.

    k-means 를 예전 중심에서 출발시키면(warm start) 군집 k 가 지난달의 군집 k
    와 같은 뜻을 유지한다. 그래야 손으로 붙인 이름과 팔레트가 계속 맞는다.
    t-SNE 는 회전·반사가 임의로 정해지므로, 겹치는 글들을 기준으로 예전 지도에
    맞춰 돌려 놓는다(프로크루스테스). 그래야 달마다 지도가 뒤집히지 않는다."""
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    from sklearn.cluster import KMeans

    cent0 = np.load(f'{B}/model/centroids.npy')
    MERGE = {int(k): v for k, v in meta['merge'].items()}

    P = PCA(n_components=min(50, V.shape[1], len(rows) - 1), random_state=0).fit_transform(V)
    XY = TSNE(n_components=2, perplexity=30, init='pca', random_state=0,
              learning_rate='auto', metric='cosine').fit_transform(P)
    XY = ((XY - XY.mean(0)) / XY.std(0)).astype(np.float32)

    prev = {str(i): xy for i, xy in zip(anc['ids'], anc['xy'])}
    shared = [i for i, r in enumerate(rows) if r['id'] in prev]
    if len(shared) >= 20:
        A = XY[shared] - XY[shared].mean(0)
        Bm = np.array([prev[rows[i]['id']] for i in shared], dtype=np.float32)
        Bm = Bm - Bm.mean(0)
        U, _, Vt = np.linalg.svd(A.T @ Bm)
        R = U @ Vt                      # 직교 — 회전과 반사만, 늘이지 않는다
        XY = (XY - XY[shared].mean(0)) @ R
        moved = np.linalg.norm(XY[shared] - Bm, axis=1)
    else:
        moved = np.array([0.0])

    km = KMeans(n_clusters=meta['k_raw'], init=cent0, n_init=1, random_state=0).fit(V)
    lab = np.array([MERGE[int(c)] for c in km.labels_], dtype=np.int16)

    old = {str(i): int(c) for i, c in zip(anc['ids'], anc['cluster'])}
    kept = [lab[i] == old[r['id']] for i, r in enumerate(rows) if r['id'] in old]
    for i, r in enumerate(rows):
        r['xy'], r['c'] = XY[i], int(lab[i])
    return dict(centroids=km.cluster_centers_.astype(np.float32), V=V, XY=XY, lab=lab,
                kept=float(np.mean(kept)) if kept else 1.0,
                moved=float(np.median(moved)),
                raw_sizes={c: int((km.labels_ == c).sum()) for c in range(meta['k_raw'])})


# ── 2b. --freeze: 예전 지도를 그대로 두고 새 글만 투영한다 ───────────────
def freeze(rows, V, meta, anc):
    A_vec, A_xy, A_cl = anc['vec'].astype(np.float32), anc['xy'], anc['cluster']
    have = {str(i): k for k, i in enumerate(anc['ids'])}
    cent = np.load(f'{B}/model/centroids.npy')
    MERGE = {int(k): v for k, v in meta['merge'].items()}
    knn, power = meta['knn'], meta['power']
    sims = []
    for i, r in enumerate(rows):
        if not r['new']:
            k = have[r['id']]
            r['xy'], r['c'] = A_xy[k], int(A_cl[k])
            continue
        c = int(np.argmin(((V[i] - cent) ** 2).sum(1)))
        s = V[i] @ A_vec.T
        idx = np.argpartition(-s, knn)[:knn]
        sv = s[idx]
        w = np.clip(sv - sv.min(), 0, None) ** power
        w = w / w.sum() if w.sum() > 0 else np.full(knn, 1 / knn)
        r['xy'] = (A_xy[idx] * w[:, None]).sum(0) + jitter(r['id'])
        r['c'] = MERGE[c]
        r['sim'] = float(sv.max())
        sims.append(r['sim'])
    return sims


def jitter(pid, amp=0.03):
    h = hashlib.sha1(pid.encode()).digest()
    return np.array([(h[0] / 255 - .5), (h[1] / 255 - .5)]) * 2 * amp


# ── 3. 결과물 ────────────────────────────────────────────────────────────
def viz_of(rows, meta, terms):
    months = sorted({r['month'] for r in rows})
    comp = defaultdict(Counter)
    for r in rows:
        comp[r['month']][r['c']] += 1
    K = len(meta['names'])
    return dict(
        points=[dict(x=round(float(r['xy'][0]), 3), y=round(float(r['xy'][1]), 3), c=r['c'],
                     m=r['month'], d=r['day'], t=r['text'][:200], f=r['fav'], i=r['id'])
                for r in rows],
        clusters=terms, names=meta['names'], descs=meta['descs'],
        sizes={str(c): sum(1 for r in rows if r['c'] == c) for c in range(K)},
        months=months,
        comp={m: {str(c): comp[m][c] for c in range(K)} for m in months},
        links={m: link_tally([r for r in rows if r['month'] == m]) for m in months},
        linksum=link_summary(rows, K),
    )


NAVER = ('naver.me', 'n.news.naver.com', 'news.naver.com', 'm.news.naver.com',
         'blog.naver.com', 'm.site.naver.com')
DAUM = ('v.daum.net', 'daum.net', 'm.daum.net', 'news.daum.net')


def link_summary(rows, K):
    """'읽히는 것' 문단이 인용하는 전체 집계. 페이지가 스스로 갱신되도록
    파이썬에서 계산해 넣는다."""
    H = [r for r in rows if r['u'] is not None]
    ext = [(r, u) for r in H for u in r['u'] if host_of(u) not in SELF + VIDEO]
    arg = [(r, u) for r, u in ext if r['c'] == 8]
    byc = {}
    for c in range(K):
        S = [r for r in H if r['c'] == c]
        byc[str(c)] = dict(
            ext=sum(1 for r in S if any(host_of(u) not in SELF + VIDEO for u in r['u'])),
            vid=sum(1 for r in S for u in r['u'] if host_of(u) in VIDEO))
    return dict(
        ext=len(ext),
        daum=sum(1 for _, u in ext if host_of(u) in DAUM),
        naver=sum(1 for _, u in ext if host_of(u) in NAVER),
        argext=len(arg),
        argdaum=sum(1 for _, u in arg if host_of(u) in DAUM),
        byc=byc)


def link_tally(R):
    """그 달의 링크·미디어 집계. 원래 주소를 모르는 글은 known 에서 빠진다."""
    H = [r for r in R if r['u'] is not None]
    ext = [r for r in H if any(host_of(u) not in SELF + VIDEO for u in r['u'])]
    vid = [u for r in H for u in r['u'] if host_of(u) in VIDEO]
    return dict(n=len(R), known=len(H), ext=len(ext), video=len(vid),
                media=sum(1 for r in H if r['md']))


def cluster_terms(rows, K):
    df, cl = Counter(), defaultdict(Counter)
    for r in rows:
        ts = toks(r['text'])
        df.update(set(ts))
        cl[r['c']].update(ts)
    N, out = len(rows), {}
    for c in range(K):
        tot = sum(cl[c].values()) or 1
        sc = {w: (n / tot) * np.log(N / (1 + df[w])) for w, n in cl[c].items() if n >= 3}
        out[str(c)] = [w for w, _ in sorted(sc.items(), key=lambda x: -x[1])[:8]]
    return out


def render(viz, rows, meta, collected):
    months = viz['months']
    last = months[-1]
    ym = lambda m: m.replace('-', '.')
    nmon = (int(last[:4]) - int(months[0][:4])) * 12 + int(last[5:]) - int(months[0][5:]) + 1
    peak = max(max(v.values()) for v in viz['comp'].values())
    days = {last: max(int(r['day'][8:]) for r in rows if r['month'] == last)}
    # 그 달 말일 하루 전까지 글이 있으면 완전한 달로 본다
    import calendar
    full_month = days[last] >= calendar.monthrange(int(last[:4]), int(last[5:]))[1] - 1
    tok = {
        '{{RANGE_DOT}}': f'{ym(months[0])} – {ym(last)}',
        '{{RANGE_TIGHT}}': f'{ym(months[0])}–{ym(last)}',
        '{{N}}': f'{len(rows):,}',
        '{{MONTHS}}': str(nmon),
        '{{COLLECTED}}': collected,
        '{{YMAX}}': str(max(40, -(-peak // 10) * 10)),
        '{{LAST_MON}}': str(int(last[5:])),
        '{{AXIS_FROM}}': ym(months[0])[2:],
        '{{AXIS_TO}}': ym(last)[2:],
        '{{DAYS}}': '{}' if full_month else json.dumps(days),
        '{{READINGS}}': open(f'{B}/tpl/readings.html').read().rstrip(),
    }
    blob = json.dumps(viz, ensure_ascii=False, separators=(',', ':'))

    def fill(*parts):
        s = ''.join(open(f'{B}/tpl/{p}').read() for p in parts)
        for k, v in tok.items():
            s = s.replace(k, v)
        left = re.findall(r'\{\{[A-Z_]+\}\}', s)
        if left:
            raise SystemExit(f'채우지 못한 토큰: {set(left)}')
        return s

    # map_head 는 <script id="viz"> 를 열지 않고 끝난다 — 여기서 열고 닫는다.
    # embed_head 는 열어 둔 채로 끝나고 embed_tail 이 </script> 로 시작한다.
    m = (fill('map_head.html') + '<script id="viz" type="application/json">\n'
         + blob + '\n</script>\n' + fill('map_tail.html'))
    e = fill('embed_head.html') + blob + '\n' + fill('embed_tail.html')
    for name, s in (('map', m), ('embed', e)):
        if s.count('id="viz"') != 1 or '<script id="viz" type="application/json">\n{' not in s:
            raise SystemExit(f'{name}: viz 스크립트 태그가 깨졌습니다')
    return m, e, days, full_month


def host_of(u):
    h = re.sub(r'^www\.', '', (u.split('/')[2] if '://' in u else u).lower())
    return h.split(':')[0]


def write_links(rows):
    """링크를 도메인별로 풀어 쓴다.

    본문의 링크는 t.co 로 단축돼 있어 도메인을 알 수 없다. 수집기가 저장한
    expanded_url(`u`)이 있는 글만 분해할 수 있고, 그 필드가 없는 글은
    '미수집'으로 센다. 전수로 보려면 collect_x.js 로 다시 수집해야 한다."""
    d = f'{B}/repo/data'
    have = [r for r in rows if r['u'] is not None]
    with open(f'{d}/links.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['tweet_id', 'datetime_kst', 'kind', 'domain', 'url'])
        for r in have:
            for u in r['u']:
                h = host_of(u)
                kind = ('unknown' if h == 't.co' else 'self' if h in SELF
                        else 'video' if h in VIDEO else 'external')
                w.writerow([r['id'], r['ts'][:16].replace('T', ' '), kind, h, u])

    months = sorted({r['month'] for r in rows})
    tally = {}
    for m in months:
        R = [r for r in rows if r['month'] == m]
        H = [r for r in R if r['u'] is not None]
        ext = [u for r in H for u in r['u'] if host_of(u) not in SELF + VIDEO]
        vid = [u for r in H for u in r['u'] if host_of(u) in VIDEO]
        tally[m] = dict(posts=len(R), known=len(H),
                        with_ext=sum(1 for r in H if any(host_of(u) not in SELF + VIDEO for u in r['u'])),
                        ext=len(ext), video=len(vid),
                        media=sum(1 for r in H if r['md']))
    with open(f'{d}/monthly_links.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['month', 'posts_analyzed', 'urls_known', 'posts_with_external_link',
                    'external_links', 'video_links', 'posts_with_media'])
        for m in months:
            t = tally[m]
            w.writerow([m, t['posts'], t['known'], t['with_ext'],
                        t['ext'], t['video'], t['media']])

    dom = Counter(host_of(u) for r in have for u in r['u']
                  if host_of(u) not in SELF + VIDEO)
    with open(f'{d}/link_domains.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['domain', 'links'])
        w.writerows(dom.most_common())
    return len(have), len(rows), dom


def write_data(viz, rows, meta, days):
    d = f'{B}/repo/data'
    names = meta['names']
    K = len(names)
    with open(f'{d}/posts.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['tweet_id', 'datetime_kst', 'cluster', 'cluster_label',
                    'tsne_x', 'tsne_y', 'likes', 'is_reply', 'is_quote', 'url'])
        for r in rows:
            w.writerow([r['id'], r['ts'][:16].replace('T', ' '), r['c'], names[str(r['c'])],
                        round(float(r['xy'][0]), 3), round(float(r['xy'][1]), 3),
                        r['fav'], int(r['rp']), int(r['q']),
                        f'https://x.com/{HANDLE}/status/{r["id"]}'])
    with open(f'{d}/clusters.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['cluster', 'label', 'size', 'top_terms'])
        for c in range(K):
            w.writerow([c, names[str(c)], viz['sizes'][str(c)], ' '.join(viz['clusters'][str(c)])])
    with open(f'{d}/monthly_composition.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['month', 'total'] + [names[str(c)] for c in range(K)])
        for m in viz['months']:
            v = viz['comp'][m]
            w.writerow([m, sum(v.values())] + [v[str(c)] for c in range(K)])

    full = json.load(open(f'{B}/posts_full.json'))
    mo, rep, act = Counter(), Counter(), defaultdict(set)
    for p in full.values():
        m = p['t_iso'][:7]
        mo[m] += 1
        act[m].add(p['t_iso'][:10])
        if p.get('rp'):
            rep[m] += 1
    # 원자료가 있는 달은 다시 세고, 그보다 앞선 달만 고정된 과거 집계에서 가져온다
    first_raw = min(mo)
    hist = [r for r in csv.reader(open(f'{B}/monthly_hist.csv'))][1:]
    rows_out = [r for r in hist if r[0] < first_raw]
    rows_out += [[m, mo[m], rep[m], len(act[m])] for m in sorted(mo)]
    for p in (f'{d}/monthly_counts.csv', f'{B}/monthly.csv'):
        with open(p, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['month', 'posts', 'replies', 'active_days'])
            w.writerows(rows_out)
    return sum(int(r[1]) for r in rows_out), len(rows_out), rows_out[0][0]


def patch_readme(months_total, posts_total, viz, rows, collected, days, hist_first):
    p = f'{B}/repo/README.md'
    s = open(p).read()
    last, first = viz['months'][-1], viz['months'][0]
    nmon = (int(last[:4]) - int(first[:4])) * 12 + int(last[5:]) - int(first[5:]) + 1
    reps = [
        (r'\d+개월, [\d,]+건의 월별 집계', f'{months_total}개월, {posts_total:,}건의 월별 집계'),
        (r'취임 이후 \d+개월\(\S+ ~ \S+\) [\d,]+건',
         f'취임 이후 {nmon}개월({first} ~ {last}) {len(rows):,}건'),
        # 이 줄은 63개월 집계 전체의 범위다. 군집 분석 구간(first)이 아니라
        # 월별 집계의 첫 달(hist_first)을 써야 한다.
        (r'20\d\d년 \d+월부터 20\d\d년 \d+월까지',
         f'{hist_first[:4]}년 {int(hist_first[5:])}월부터 {last[:4]}년 {int(last[5:])}월까지'),
        (r'취임 후 [\d,]+건의 ID', f'취임 후 {len(rows):,}건의 ID'),
        (r'\*\*20\d\d년 \d+월은 \d+일까지의 부분 집계입니다\.\*\*',
         f'**{last[:4]}년 {int(last[5:])}월은 {days[last]}일까지의 부분 집계입니다.**'
         if days.get(last) else '**이 저장소의 마지막 달은 완전한 달입니다.**'),
    ]
    miss = []
    for pat, new in reps:
        s, n = re.subn(pat, new, s, count=1)
        if not n:
            miss.append(pat)
    open(p, 'w').write(s)

    q = f'{B}/repo/data/README.md'
    t, n = re.subn(r'수집 시점: 20\d\d-\d\d-\d\d', f'수집 시점: {collected}',
                   open(q).read(), count=1)
    if n:
        open(q, 'w').write(t)
    else:
        miss.append('data/README.md 수집 시점')
    return miss


# ── 실행 ────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--add', help='새로 내려받은 수집 JSON')
    ap.add_argument('--check', action='store_true', help='아무것도 쓰지 않고 보고만 한다')
    ap.add_argument('--collected', help='수집일 (기본: 가장 늦은 게시물의 날짜)')
    ap.add_argument('--freeze', action='store_true',
                    help='지도를 다시 적합하지 않고 새 글만 예전 지형에 투영한다')
    a = ap.parse_args()

    meta = json.load(open(f'{B}/model/meta.json'))
    anc = np.load(f'{B}/model/anchors.npz')

    if a.add:
        full, added = merge(a.add)
        if not a.check:
            json.dump(full, open(f'{B}/posts_full.json', 'w'), ensure_ascii=False)
    else:
        full, added = json.load(open(f'{B}/posts_full.json')), 0

    rows, V, dropped, n_new = prepare(full, meta, anc, stored=a.freeze)
    fit = None
    if a.freeze:
        sims = freeze(rows, V, meta, anc)
    else:
        sims = []
        fit = refit(rows, V, meta, anc)
    terms = cluster_terms(rows, len(meta['names']))
    viz = viz_of(rows, meta, terms)
    m_html, e_html, days, full_month = render(viz, rows, meta,
                                              a.collected or rows[-1]['day'])

    print(f"분석 {len(rows)}건 (본문이 짧아 제외 {dropped}건) · "
          f"{viz['months'][0]} ~ {viz['months'][-1]} {len(viz['months'])}개월")
    print('군집:', '  '.join(f"{meta['names'][str(c)]} {viz['sizes'][str(c)]}"
                            for c in range(len(meta['names']))))
    if fit:
        print(f"새로 적합 · 예전 라벨 유지율 {fit['kept']:.1%} · "
              f"겹치는 글이 움직인 거리 중위 {fit['moved']:.2f} (지도 표준편차 = 1)")
        thin = {c: n for c, n in fit['raw_sizes'].items() if n < 5}
        if thin:
            print(f'  ! 원본 군집이 비었습니다: {thin} — 군집 수를 줄일 때입니다')
    if n_new and sims:
        print(f'투영된 새 글 {n_new}건 · 최근접 기준점 유사도 중위 {np.median(sims):.3f} '
              f'· 최저 {min(sims):.3f}')
    if n_new and not a.freeze:
        print(f'새 글 {n_new}건')
    far = [r for r in rows if r.get('new') and r.get('sim', 1) < 0.55]
    if far:
        print(f'  ! 기존 어느 글과도 닮지 않은 글 {len(far)}건 — 새 화제일 수 있습니다:')
        for r in far[:5]:
            print(f"    {r['day']} {r['text'][:60]}")

    if a.check:
        print('\n--check 이므로 아무것도 쓰지 않았습니다.')
        return

    if fit:
        import shutil
        shutil.rmtree(f'{B}/model_prev', ignore_errors=True)
        shutil.copytree(f'{B}/model', f'{B}/model_prev')
        np.savez_compressed(f'{B}/model/anchors.npz',
                            ids=np.array([r['id'] for r in rows]),
                            vec=fit['V'].astype(np.float16),
                            xy=fit['XY'], cluster=fit['lab'])
        np.save(f'{B}/model/centroids.npy', fit['centroids'])
        meta2 = dict(meta, anchors=len(rows), fit_at=rows[-1]['day'], terms=terms)
        json.dump(meta2, open(f'{B}/model/meta.json', 'w'), ensure_ascii=False, indent=1)

    json.dump(viz, open(f'{B}/viz.json', 'w'), ensure_ascii=False)
    open(f'{B}/repo/docs/map.html', 'w').write(m_html)
    open(f'{B}/repo/docs/embed.html', 'w').write(e_html)
    total, nmonths, hist_first = write_data(viz, rows, meta, days)
    nhave, nall, dom = write_links(rows)
    miss = patch_readme(nmonths, total, viz, rows, a.collected or rows[-1]['day'],
                        days, hist_first)
    print(f'\n월별 집계 {nmonths}개월 {total:,}건 · docs/ 와 data/ 를 다시 썼습니다.')
    print(f'링크: 원래 주소를 아는 글 {nhave}/{nall}건 ({nhave / nall:.0%})', end='')
    if dom:
        print(' · 외부 도메인 상위', ', '.join(f'{h} {n}' for h, n in dom.most_common(5)))
    else:
        print(' — 분해할 링크가 없습니다')

    # ── 사람이 직접 봐야 하는 것들 ──
    todo = []
    if fit and fit['kept'] < 0.9:
        todo.append(f"예전 라벨 유지율이 {fit['kept']:.0%}로 떨어졌습니다. "
                    'data/clusters.csv 의 특징어를 보고 군집 이름이 아직 맞는지 확인하세요.')
    if nhave < nall:
        todo.append(f'링크의 원래 주소가 없는 글이 {nall - nhave}건입니다. '
                    'collect_x.js 로 그 구간을 다시 수집하면 채워집니다.')
    if a.freeze and n_new and n_new > meta['anchors'] * 0.5:
        todo.append(f"--freeze 로 넣은 새 글이 기준점({meta['anchors']}건)의 절반을 넘었습니다. "
                    '--freeze 없이 한 번 돌릴 때입니다.')
    last = viz['months'][-1]
    ref = re.findall(r"'(20\d\d-\d\d)'", open(f'{B}/tpl/readings.html').read())
    if ref and max(ref) < last:
        todo.append(f"tpl/readings.html('읽히는 것')이 {max(ref)} 기준입니다. {last} 로 고쳐야 합니다.")
    if not full_month:
        todo.append(f'{last}은 {days[last]}일까지의 부분 집계입니다. '
                    'README 한계 항목의 날짜를 확인하세요.')
    if miss:
        todo.append(f'README 에서 못 고친 자리: {miss}')
    if todo:
        print('\n손으로 고칠 것')
        for t in todo:
            print(' -', t)


if __name__ == '__main__':
    main()
