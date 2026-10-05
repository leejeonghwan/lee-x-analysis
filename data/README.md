# 데이터 노트

X 이용약관은 게시물 본문의 대량 재배포를 제한하고 ID 공유를 권장합니다.
이 폴더에는 **게시물 ID와 파생 지표만** 들어 있습니다. 본문은 없습니다.

본문이 필요하면 저장소 루트의 `collect/collect_x.js` 로 직접 수집하십시오.
`data/posts.csv` 의 `url` 컬럼으로 개별 원문을 확인할 수 있습니다.

`tweet_id` 는 19자리 숫자입니다. 스프레드시트나 pandas 에서 정수로 읽으면
정밀도가 깨지므로 **반드시 문자열로 읽으십시오**.

```python
import pandas as pd
df = pd.read_csv('posts.csv', dtype={'tweet_id': str})
```

수집 시점: 2026-10-05
