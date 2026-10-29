"""build_auto.py — collect_x.js + collect/_auto_tail.js → collect/collect_auto.js

콘솔에 한 번 붙여넣으면 알아서 수집하고 내려받기 버튼까지 띄우는 파일을 만든다.
수집 논리를 두 벌로 들고 있지 않기 위해 합쳐서 생성한다.
"""
import os, datetime

B = os.path.dirname(os.path.abspath(__file__))
head = open(f'{B}/collect/collect_x.js').read()
tail = open(f'{B}/collect/_auto_tail.js').read()

out = f"""/* collect_auto.js — 생성된 파일입니다. 고치지 마십시오.
 * 원본: collect/collect_x.js + collect/_auto_tail.js
 * 생성: build_auto.py ({datetime.date.today()})
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

{head}

{tail}
"""
open(f'{B}/collect/collect_auto.js', 'w').write(out)
print('collect/collect_auto.js', len(out), 'bytes')
