# GNS Monitor — 정적 배포본 (GitHub Pages)

경영진이 링크 하나로 모바일·PC에서 보는 제뉴원 내/외부 환경 모니터. 서버 없이 동작하며,
**화면·메뉴·기능은 사내 모니터(localhost:5001)와 동일**하다. 사내 데이터를 갱신하고 `publish.bat` 을 누르면 링크에 반영된다.

링크: https://daeyeongmun.github.io/gns-monitor-site/ (비밀번호는 담당자에게)

## 어떻게 같은 화면이 서버 없이 도는가
```
사내 모니터 서버 (Flask, localhost:5001)
   │  build_static.py — 대시보드 원본(dashboard/index.html)을 그대로 가져오고,
   │                    대시보드가 호출하는 모든 /api/… 응답(기업 62사 × 전 메뉴, 품목 전수, 성분 649개 …)을 긁어
   ▼                    청크 단위로 gzip → AES-256-GCM 봉인
docs/index.html   비밀번호 화면 + 봉인된 대시보드 + fetch 가로채기(shim)
docs/d/*.enc      봉인 청크 (core / products_연도 / ingr_연도 / oppty_연도 / co_N / pd_N / pq_N / mol_N / bl)
docs/live.enc     GitHub Actions 가 매일 07:30(KST) 공시·주가·뉴스를 긁어 봉인 → 열람 시 이슈/뉴스/주가에 겹쳐 표시
```
브라우저에서 비밀번호를 넣으면 키를 만들고, 대시보드가 `fetch('/api/…')` 를 부를 때마다 해당 청크를 내려받아 풀어 응답한다.
POST(스냅샷 저장·업로드·조사 실행)만 "서버판 전용" 으로 막힌다.

## 운영
- **사내 데이터 갱신 → 반영**: `GenuoneMonitor_DevPackage/data/` 파일 교체 → 모니터 서버 재시작 → `publish.bat` 실행.
  수집 결과는 `build/cache/` 에 남아 다음 빌드에 재사용된다 (평문, 저장소에 올라가지 않음).

  | 실행 | 다시 긁는 것 | 소요 | 언제 |
  |---|---|---|---|
  | `publish.bat` (기본) | 기본·연도별(품목/주성분/수주전환)·설비·특화모델 요약 | 약 10분 | 수익성·IQVIA·잔고 파일을 바꿨을 때 |
  | `publish.bat --quick` | 캐시에 없는 것만 | 수 분 | 화면(index.html)만 고쳤을 때 |
  | `publish.bat --fresh` | 전부 (기업 62사·품목 전수·성분 상세 포함) | 약 4시간 | 전수DB·약가·기업 기준정보까지 바뀐 뒤, 야간에 |
- **공시·주가·뉴스**: Actions `live-refresh` 가 매일 자동. 사용자 PC가 꺼져 있어도 돈다. 수동 실행은 Actions 탭.
- **비밀번호 변경**: `build_static.py`/`encrypt.py` 의 기본값(또는 환경변수 `SITE_PASSWORD`)과 Actions secret `SITE_PASSWORD` 를 같이 바꾸고 publish.

## 저장소 설정 (완료 상태)
- 저장소 `DaeyeongMun/gns-monitor-site` (public) · Pages: main `/docs` · Secrets: `DART_API_KEY`, `DATA_GO_KR_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `SITE_PASSWORD`.
- 평문은 올라가지 않는다 (`build/` 는 .gitignore). `docs/` 에는 봉인본만 있다.

## 보안 메모
- 봉인은 AES-256-GCM(PBKDF2 20만회). 비밀번호를 아는 사람만 연다. 페이지 URL 자체는 공개이므로 비밀번호 관리가 전부다.
- 클라이언트 복호화라 비밀번호가 새면 데이터도 샌다. 경영진 전용 비밀번호를 쓰고 인사 변동 시 바꿔 재배포.
