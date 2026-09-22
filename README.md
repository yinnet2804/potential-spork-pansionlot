# pansion_lot

연금복권720+ 참고용 번호 조합 생성기 + 과거 회차 통계.

빌드 과정이 없는 정적 사이트입니다. `index.html` 하나에 마크업·스타일·스크립트가
모두 들어 있고, 회차 데이터는 `data/pension720.json`에서 읽습니다. Cloudflare Pages가
`main` 브랜치를 그대로 서빙합니다.

## 배포

https://potential-spork-pansionlot.pages.dev/

`main`에 푸시하면 Cloudflare Pages가 자동으로 재배포합니다.

## 구성

```
pansion_lot/
├─ index.html                번호 생성 + 당첨 구조 + 통계 (단일 페이지)
├─ crawler.py                동행복권 당첨번호 수집기
├─ requirements.txt          크롤러 의존성
├─ data/pension720.json      수집 결과 (페이지가 읽는 유일한 데이터)
└─ .github/workflows/
   └─ update-data.yml        매주 목요일 자동 수집·커밋
```

## 번호 생성

한 장은 조(1~5)와 6자리 번호(000000~999999)로 이루어집니다. 페이지를 열거나
"다시 생성"을 누르면 조합 5개를 새로 뽑습니다.

번호는 `crypto.getRandomValues`로 만들고, 나머지 연산에서 생기는 편향은 거부
표집으로 제거해 균등 분포를 보장합니다.

> ⚠ 추첨은 회차마다 독립적인 무작위 사건이라 과거 데이터로 다음 회차를 예측할 수
> 없습니다. 생성되는 조합은 예측이 아니라 무작위이며, 당첨 확률은 아무 번호나
> 직접 고르는 것과 동일합니다. 아래 통계도 지나간 결과의 요약일 뿐입니다.

## 통계

`data/pension720.json`을 읽어 브라우저에서 계산합니다.

- **1등 조 분포** — 조별 1등 출현 횟수. 균등했을 때의 기대 횟수를 세로선으로 함께 표시합니다.
- **자리별 숫자 출현 횟수** — 1등 6자리를 자리마다 따로 집계한 히트맵.
- **최근 10회 당첨번호** — 회차·추첨일·1등·보너스.

## 데이터 수집

```
pip install -r requirements.txt
python crawler.py
```

동행복권 결과 페이지(`/pt720/result`)가 쓰는 두 엔드포인트를 호출합니다.

- `selectPstPt720WnList.do` — 파라미터 없이 전 회차를 한 번에 반환하므로 회차별
  반복 요청이 필요 없습니다.
- `selectPstPt720Info.do` — 등위별 당첨금. 금액은 회차와 무관하게 고정이라
  최신 회차 것만 읽습니다.

수집한 값은 회차 연속성, 조 범위(1~5), 6자리 형식을 검증한 뒤 저장합니다.
회차와 당첨금이 이전과 같으면 파일을 다시 쓰지 않습니다(수집 시각만 바뀐 경우는
변경으로 보지 않음).

## 자동 갱신

`.github/workflows/update-data.yml`이 매주 크롤러를 돌리고, 새 회차가 있으면
`data/pension720.json`을 커밋합니다. 그 푸시를 Cloudflare Pages가 받아 사이트를
다시 배포하므로 별도 조작이 필요 없습니다.

| 시점 | UTC cron | 목적 |
|---|---|---|
| 목 21:30 KST | `30 12 * * 4` | 추첨 당일 갱신 |
| 금 09:00 KST | `0 0 * * 5` | 결과 반영 지연·실행 누락 대비 재시도 |

내용이 같으면 커밋하지 않으므로 두 번 실행돼도 중복 커밋은 생기지 않습니다.
Actions 페이지의 **Run workflow**로 수동 실행할 수도 있습니다.

> 저장소 Settings → Actions → General → Workflow permissions가
> **Read and write permissions**여야 푸시가 됩니다. 읽기 전용이면 마지막
> `git push` 단계에서 403으로 실패합니다.
>
> GitHub은 60일간 저장소 활동이 없으면 예약 워크플로를 자동으로 중지합니다.
> 매주 커밋이 생기는 동안은 해당되지 않습니다.

## 로컬 실행

`fetch`로 JSON을 읽기 때문에 `file://`로 열면 통계가 표시되지 않습니다.
간단한 로컬 서버로 여세요.

```
python -m http.server 8000
```

http://127.0.0.1:8000/

## 라이선스

미정.
