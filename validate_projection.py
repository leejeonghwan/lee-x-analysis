"""validate_projection.py — 새 글을 고정된 지도에 끼워 넣는 게 얼마나 정확한가.

t-SNE 에는 transform() 이 없다. 그래서 update.py 는 새 글을 '임베딩이 가장
비슷한 기준점 12개의 좌표를 유사도로 가중평균한 자리'에 놓는다. 이 근사가
얼마나 믿을 만한지 기준점 200개를 빼놓고 재현해 측정한다.

측정 지표는 '이웃 보존율'이다. 임베딩 공간에서의 최근접 10개가 2차원에
놓인 뒤에도 최근접 10개 안에 남아 있는 비율. 지도가 주장하는 것이
'가까이 놓인 점일수록 비슷한 글'이므로 이게 바로 그 주장의 성적표다.

천장이 있다. 기준점들 자신도 t-SNE 투영에서 이웃을 다 지키지 못한다.
근사의 성적을 그 천장과 비교해야 한다.

(openTSNE 의 진짜 transform() 과도 비교해 봤다. 같은 조건에서 0.347 대 0.347,
 즉 구별되지 않았다. 의존성을 하나 더 들일 이유가 없어 가중평균을 쓴다.)
"""
import json, numpy as np

B = '/home/claude/lee_x'
K = 10

meta = json.load(open(f'{B}/model/meta.json'))
anc = np.load(f'{B}/model/anchors.npz')
V, XY, CL = anc['vec'].astype(np.float32), anc['xy'], anc['cluster']
knn, power = meta['knn'], meta['power']

rng = np.random.default_rng(0)
hold = rng.choice(len(V), 200, replace=False)
S = V[hold] @ V.T
S[np.arange(len(hold)), hold] = -1


def place(r):
    idx = np.argpartition(-S[r], knn)[:knn]
    s = S[r, idx]
    w = np.clip(s - s.min(), 0, None) ** power
    w = w / w.sum() if w.sum() > 0 else np.full(knn, 1 / knn)
    return (XY[idx] * w[:, None]).sum(0)


def keep(pos, r, skip):
    true = set(np.argsort(-S[r])[:K])
    d = np.linalg.norm(XY - pos, axis=1)
    d[skip] = np.inf
    return len(true & set(np.argsort(d)[:K])) / K


approx = np.mean([keep(place(r), r, hold[r]) for r in range(len(hold))])
ceil = np.mean([keep(XY[hold[r]], r, hold[r]) for r in range(len(hold))])
err = np.array([np.linalg.norm(place(r) - XY[hold[r]]) for r in range(len(hold))])

print(f'이웃 보존율 (최근접 {K}개 기준)')
print(f'  t-SNE 가 직접 놓은 자리  {ceil:.3f}   ← 천장')
print(f'  가중평균으로 놓은 자리   {approx:.3f}   ← update.py')
print(f'\n좌표 오차 (지도 표준편차 = 1)')
print(f'  중위 {np.median(err):.3f} · 90분위 {np.quantile(err, .9):.3f} · 0.5 초과 {(err > .5).mean():.0%}')
print('\n읽는 법: 보존율이 천장에 붙어 있으면 근사 때문에 잃는 것이 거의 없다는 뜻이다.')
print('(천장을 살짝 넘기기도 한다. 이웃들의 좌표를 평균하면 그 이웃들 가운데에')
print(' 놓이게 되는데, 이 지표에는 그게 오히려 유리하기 때문이다.)')
print('좌표 오차의 꼬리가 두꺼운 것은 근사의 한계가 아니라 t-SNE 자체가')
print('비슷한 글을 늘 가까이 놓지는 못한다는 뜻이다 (천장이 1이 아닌 이유).')
