# 데이터 노트

X 이용약관은 게시물 본문의 대량 재배포를 제한하고 ID 공유를 권장합니다.
이 폴더에는 **게시물 ID와 파생 지표만** 들어 있습니다. 본문은 없습니다.
(지도 페이지 `docs/`에는 마우스오버용 200자 발췌가 별도로 들어 있습니다.)

본문이 필요하면 저장소 루트의 `collect/collect_x.js` 로 직접 수집하십시오.
`data/posts.csv` 의 `url` 컬럼으로 개별 원문을 확인할 수 있습니다.

## 링크 파일

| 파일 | 내용 |
|---|---|
| `links.csv` | 게시물별 링크 한 줄씩 — `tweet_id, datetime_kst, kind, domain, url` |
| `link_domains.csv` | 외부 도메인별 링크 수 |
| `monthly_links.csv` | 월별 링크·미디어 집계 |

`kind` 는 넷입니다.

```
external  외부 사이트 (언론사·정부 등)
video     유튜브
self      x.com — 자기 글이나 인용한 원글
unknown   t.co — 펼쳐지지 않은 단축 주소
```

본문의 링크는 X가 `t.co` 로 단축해 보여주므로 도메인을 알 수 없습니다.
수집기는 `entities.urls[].expanded_url` 에서 원래 주소를 꺼내 저장하는데,
**2026년 10월 이전에 수집한 글에는 이 필드가 없습니다.** `monthly_links.csv`
의 `urls_known` 이 그 달에 원래 주소를 아는 글 수이고, `posts_analyzed` 보다
작으면 그만큼이 미수집입니다. 전수로 채우려면 `collect/collect_x.js` 로 그
구간을 다시 수집하십시오(`UPDATE.md` 0-1 참조).

첨부 사진·동영상은 링크가 아니라 `media` 로 오기 때문에 `posts_with_media`
로 따로 셉니다. 예전처럼 본문의 `t.co` 개수를 세면 기사 링크와 사진 첨부가
섞입니다.

`tweet_id` 는 19자리 숫자입니다. 스프레드시트나 pandas 에서 정수로 읽으면
정밀도가 깨지므로 **반드시 문자열로 읽으십시오**.

```python
import pandas as pd
df = pd.read_csv('posts.csv', dtype={'tweet_id': str})
```

수집 시점: 2026-10-29
