import json, re, html, sys, numpy as np
from collections import Counter, defaultdict
from model2vec import StaticModel
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans

RAW = json.load(open('/home/claude/lee_x/posts_full.json'))

URL = re.compile(r'https?://\S+')
MENT = re.compile(r'@\w+')
FOOT = re.compile(r'[-–]\s*이재명 후원회.*', re.S)

rows = []
for pid, d in RAW.items():
    t = html.unescape(d['x'])
    t = FOOT.sub('', t)
    t = URL.sub(' ', t)
    t = MENT.sub(' ', t)
    t = re.sub(r'[<>]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    if len(t) < 8:
        continue
    ts = np.datetime64(d['t_iso'])
    rows.append(dict(id=pid, ts=str(ts), month=str(ts)[:7], day=str(ts)[:10],
                     text=t, fav=d.get('fav', 0), rt=d.get('rt', 0), rep=d.get('rep', 0),
                     is_reply=d.get('rp', False), is_quote=d.get('q', False)))

rows.sort(key=lambda r: r['ts'])
print('posts:', len(rows), rows[0]['month'], '->', rows[-1]['month'], file=sys.stderr)

model = StaticModel.from_pretrained('minishlab/potion-multilingual-128M')
V = model.encode([r['text'] for r in rows])
V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

P = PCA(n_components=min(50, V.shape[1], len(rows) - 1), random_state=0).fit_transform(V)
XY = TSNE(n_components=2, perplexity=30, init='pca', random_state=0,
          learning_rate='auto', metric='cosine').fit_transform(P)
XY = (XY - XY.mean(0)) / XY.std(0)

K = 8
km = KMeans(n_clusters=K, n_init=20, random_state=0).fit(V)
lab = km.labels_

# distinctive terms per cluster (class-based TF-IDF on 2-gram+ Korean tokens)
def toks(t):
    ws = re.findall(r'[가-힣]{2,8}|[A-Za-z]{3,}', t)
    return [w for w in ws if w not in STOP]

STOP = set('''있습니다 합니다 하겠습니다 드립니다 그리고 하지만 여러분 대한민국 국민 우리 오늘 지금 대통령 것입니다 위해 통해 함께 모든 더욱 정부 감사합니다 있는 있도록 하는 해서 대한 이번 관련 대해 만들 만들겠습니다 하고 해야 위한 되는 됩니다 같은 같이 다시 계속 매우 정말 많은 많이 그런 이런 저런 무엇 어떤 라며 라고 이라 에서 으로 에게 까지 부터 보다 처럼 이라고'''.split())

df = Counter()
docs = []
for r in rows:
    ts_ = set(toks(r['text']))
    docs.append(ts_)
    df.update(ts_)

cl_tf = defaultdict(Counter)
for i, r in enumerate(rows):
    cl_tf[lab[i]].update(toks(r['text']))

N = len(rows)
labels = {}
for c in range(K):
    tot = sum(cl_tf[c].values()) or 1
    sc = {}
    for w, n in cl_tf[c].items():
        if n < 3 or len(w) < 2:
            continue
        sc[w] = (n / tot) * np.log(N / (1 + df[w]))
    top = sorted(sc.items(), key=lambda x: -x[1])[:8]
    labels[c] = [w for w, _ in top]

out = dict(
    points=[dict(x=round(float(XY[i, 0]), 3), y=round(float(XY[i, 1]), 3), c=int(lab[i]),
                 m=rows[i]['month'], d=rows[i]['day'], t=rows[i]['text'][:150],
                 f=rows[i]['fav'], id=rows[i]['id'])
            for i in range(len(rows))],
    clusters={str(c): labels[c] for c in range(K)},
    sizes={str(c): int((lab == c).sum()) for c in range(K)},
)
json.dump(out, open('/home/claude/lee_x/points.json', 'w'), ensure_ascii=False)

# monthly composition
comp = defaultdict(Counter)
for i, r in enumerate(rows):
    comp[r['month']][int(lab[i])] += 1
print('\n=== cluster terms ===', file=sys.stderr)
for c in range(K):
    print(c, out['sizes'][str(c)], ' '.join(labels[c]), file=sys.stderr)
print('\n=== monthly composition ===', file=sys.stderr)
for m in sorted(comp):
    tot = sum(comp[m].values())
    print(m, tot, {c: comp[m][c] for c in range(K)}, file=sys.stderr)
json.dump({m: dict(comp[m]) for m in comp}, open('/home/claude/lee_x/comp.json', 'w'))
