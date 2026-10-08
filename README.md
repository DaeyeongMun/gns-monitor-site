# GNS Monitor — 정적 배포본 (GitHub Pages)

경영진이 링크 하나로 모바일·PC에서 보는 제뉴원 내/외부 환경 모니터. 서버 없이 동작한다.

## 구조
```
gns-site/
  build_site.py      모니터(Flask API + 로더)에서 데이터 번들 추출 → build/data.json
  site/app.html      화면 (모바일 우선, PC 사이드바) — 성분/제형/대상회사 특화 모델 포함
  encrypt.py         app.html + data.json 을 비밀번호로 봉인 → docs/index.html
  live_fetch.py      GitHub Actions 가 매일 공개 API(DART·KRX·네이버·RSS)를 긁어 docs/live.enc 생성
  publish.bat        [빌드 → 봉인 → git push] 한 번에
  docs/              GitHub Pages 가 서비스하는 폴더 (봉인된 파일만 올라감)
```

## 최초 1회 설정
1. GitHub에 저장소 생성 (예: `gns-monitor-site`, private 권장).
2. 이 폴더에서
   ```
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/<계정>/gns-monitor-site.git
   git push -u origin main
   ```
3. 저장소 Settings → Pages → Source: `Deploy from a branch`, Branch `main` / `/docs` → Save.
   링크: `https://<계정>.github.io/gns-monitor-site/`
   (private 저장소에서 Pages를 쓰려면 GitHub Pro/Team 필요. 무료 계정이면 public 저장소여야 하며,
   그래서 평문은 올리지 않고 docs/ 에는 봉인본만 둔다.)
4. Settings → Secrets and variables → Actions 에 등록:
   `DART_API_KEY`, `DATA_GO_KR_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `SITE_PASSWORD`(=열람 비밀번호)
5. Actions 탭에서 `live-refresh` 를 한 번 수동 실행 → `docs/live.enc` 생성 확인.

## 평소 운영
- 사내 데이터(IQVIA·약가·유비스트·profit 등)를 `GenuoneMonitor_DevPackage/data/` 에 교체 → 모니터 서버 실행 중인 상태에서 `publish.bat` 더블클릭. 1~2분 뒤 링크에 반영.
- 공시·주가·뉴스는 GitHub Actions 가 매일 07:30(KST) 자동 갱신. 사용자 PC가 꺼져 있어도 돈다.
- 비밀번호 변경: `encrypt.py` 의 기본값과 Actions secret `SITE_PASSWORD` 를 같이 바꾸고 다시 publish.

## 보안 메모 (정직하게)
- 봉인은 AES-256-GCM(PBKDF2 20만회). 비밀번호를 아는 사람만 연다. 페이지 자체는 공개 URL이므로 비밀번호 관리가 전부다.
- 클라이언트 복호화라 비밀번호가 유출되면 데이터도 유출된다. 경영진 전용 비밀번호를 쓰고, 퇴직 등 변동 시 바꿔서 재배포.
- 평문 데이터(build/)는 .gitignore 로 저장소에 올라가지 않는다.
