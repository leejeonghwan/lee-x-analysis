"""refit.py — 지도를 처음부터 다시 적합한다. 1년에 한 번쯤 쓸 일이 생긴다.

update.py 로 새 글을 투영해 넣는 것은 기존 지형 안에 자리를 찾아 주는 일이다.
지형 자체가 낡으면 — 기준점에 없던 화제가 늘어나면 — 다시 적합해야 한다.
그 신호는 둘이다.
  1. update.py 가 '기준점의 절반을 넘었다'고 경고한다
  2. update.py 가 '기존 어느 글과도 닮지 않은 글'을 계속 보고한다

다시 적합하면 좌표도 군집 번호도 전부 바뀐다. 그래서 이 스크립트는
model/ 을 덮지 않고 model_next/ 에 쓰고, 예전 군집과의 대응표를 출력한다.
그 표를 보고 이름을 옮겨 붙인 뒤에 손으로 교체한다.

    python3 refit.py --k 10
    # 출력된 대응표를 보고 model_next/meta.json 의 names/descs/merge 를 채운다
    mv model model_v1 && mv model_next model
    python3 update.py
"""
import json, os, re, argparse, numpy as np
from collections import Counter, defaultdict
from model2vec import StaticModel
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans

B = os.path.dirname(os.path.abspath(__file__))
import update as U                     # 전처리·특징어 추출을 그대로 쓴다

ap = argparse.ArgumentParser()
ap.add_argument('--k', type=int, default=10)
ap.add_argument('--perplexity', type=float, default=30)
a = ap.parse_args()

old_meta = json.load(open(f'{B}/model/meta.json'))
full = json.load(open(f'{B}/posts_full.json'))

rows = []
for pid, d in full.items():
    t = U.clean(d['x'])
    if len(t) >= 8:
        rows.append(dict(id=pid, ts=d['t_iso'], text=t))
rows.sort(key=lambda r: r['ts'])
print(f'{len(rows)}건 적합')

V = StaticModel.from_pretrained(old_meta['embed_model']).encode([r['text'] for r in rows])
V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
P = PCA(n_components=min(50, V.shape[1], len(rows) - 1), random_state=0).fit_transform(V)
XY = TSNE(n_components=2, perplexity=a.perplexity, init='pca', random_state=0,
          learning_rate='auto', metric='cosine').fit_transform(P)
XY = ((XY - XY.mean(0)) / XY.std(0)).astype(np.float32)

km = KMeans(n_clusters=a.k, n_init=20, random_state=0).fit(V)
lab = km.labels_.astype(np.int16)

for r, c in zip(rows, lab):
    r['c'] = int(c)
terms = U.cluster_terms(rows, a.k)

# 예전 군집과의 대응 — 겹치는 글이 가장 많은 쪽
old = {str(i): int(c) for i, c in zip(np.load(f'{B}/model/anchors.npz')['ids'],
                                      np.load(f'{B}/model/anchors.npz')['cluster'])}
cross = defaultdict(Counter)
for r in rows:
    if r['id'] in old:
        cross[r['c']][old[r['id']]] += 1

print('\n새 군집 → 예전 군집 대응 (이름을 옮겨 붙일 때 쓴다)')
for c in range(a.k):
    n = int((lab == c).sum())
    top = cross[c].most_common(3)
    share = f'{top[0][1] / sum(cross[c].values()):.0%}' if top else '-'
    hint = ', '.join(f"{old_meta['names'][str(o)]} {v}" for o, v in top) or '(새 군집)'
    print(f'  {c:>2} {n:>4}건  {share:>4} ← {hint}')
    print(f'       특징어 {" ".join(terms[str(c)])}')
    for r in [x for x in rows if x['c'] == c][:2]:
        print(f'       예시 {r["text"][:70]}')

os.makedirs(f'{B}/model_next', exist_ok=True)
np.savez_compressed(f'{B}/model_next/anchors.npz',
                    ids=np.array([r['id'] for r in rows]), vec=V.astype(np.float16),
                    xy=XY, cluster=lab)
np.save(f'{B}/model_next/centroids.npy', km.cluster_centers_.astype(np.float32))
json.dump(dict(version=old_meta['version'] + 1, frozen_at=rows[-1]['ts'][:10],
               embed_model=old_meta['embed_model'], k_raw=a.k,
               merge={str(c): c for c in range(a.k)},
               names={str(c): f'TODO-{c}' for c in range(a.k)},
               descs={str(c): 'TODO' for c in range(a.k)},
               terms=terms, anchors=len(rows),
               knn=old_meta['knn'], power=old_meta['power']),
          open(f'{B}/model_next/meta.json', 'w'), ensure_ascii=False, indent=1)
print(f'\nmodel_next/ 에 썼습니다. meta.json 의 names·descs·merge 를 채우고,')
print('색 팔레트가 군집 수에 맞는지 확인한 뒤 model/ 로 바꿔치우십시오.')
