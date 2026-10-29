"""freeze.py — 현재 분석 결과를 '고정 모델'로 저장한다.

update.py 가 새 게시물을 이 모델 안으로 투영하기 위해 필요한 것만 남긴다.
한 번 돌리면 다시 돌릴 일이 없다. 모델을 다시 적합하려면 refit.py 를 쓴다.

model/
  anchors.npz   기준점 924건: id, 임베딩(float16), 2차원 좌표, 군집 번호
  centroids.npy k-means 중심 10개 (병합 전 원본)
  meta.json     병합표, 군집 이름·설명·특징어, 파라미터, 버전
"""
import json, re, html, os, numpy as np
from model2vec import StaticModel
from sklearn.cluster import KMeans

B = '/home/claude/lee_x'
MODEL = 'minishlab/potion-multilingual-128M'
K_RAW = 10
MERGE = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 6, 9: 8}

URL = re.compile(r'https?://\S+')
MENT = re.compile(r'@\w+')
FOOT = re.compile(r'[-–]\s*이재명 후원회.*', re.S)


def clean(raw_text):
    t = html.unescape(raw_text)
    t = FOOT.sub('', t)
    t = URL.sub(' ', t)
    t = MENT.sub(' ', t)
    t = re.sub(r'[<>]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def main():
    viz = json.load(open(f'{B}/viz.json'))
    raw = json.load(open(f'{B}/posts_full.json'))

    ids = [p['i'] for p in viz['points']]
    xy = np.array([[p['x'], p['y']] for p in viz['points']], dtype=np.float32)
    lab9 = np.array([p['c'] for p in viz['points']], dtype=np.int16)

    texts = [clean(raw[i]['x']) for i in ids]
    V = StaticModel.from_pretrained(MODEL).encode(texts)
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

    km = KMeans(n_clusters=K_RAW, n_init=20, random_state=0).fit(V)
    got = np.array([MERGE[c] for c in km.labels_], dtype=np.int16)
    agree = (got == lab9).mean()
    print(f'기존 라벨 재현율 {agree:.4f}')
    if agree < 0.999:
        raise SystemExit('재현 실패 — 병합표나 전처리가 달라졌습니다')

    os.makedirs(f'{B}/model', exist_ok=True)
    np.savez_compressed(f'{B}/model/anchors.npz',
                        ids=np.array(ids), vec=V.astype(np.float16),
                        xy=xy, cluster=lab9)
    np.save(f'{B}/model/centroids.npy', km.cluster_centers_.astype(np.float32))
    json.dump(dict(version=1, frozen_at='2026-10-05', embed_model=MODEL,
                   k_raw=K_RAW, merge={str(k): v for k, v in MERGE.items()},
                   names=viz['names'], descs=viz['descs'], terms=viz['clusters'],
                   anchors=len(ids), knn=12, power=8),
              open(f'{B}/model/meta.json', 'w'), ensure_ascii=False, indent=1)
    print('model/ 에 기준점', len(ids), '건 저장')


if __name__ == '__main__':
    main()
