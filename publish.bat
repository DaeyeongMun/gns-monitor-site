@echo off
chcp 65001 >nul
cd /d %~dp0
set PY=..\GenuoneMonitor_DevPackage\.venv\Scripts\python.exe
echo [1/3] 데이터 번들 (모니터 서버가 켜져 있으면 API, 아니면 로더)
"%PY%" -X utf8 build_site.py || goto :err
echo [2/3] 비밀번호 봉인 → docs\index.html
"%PY%" -X utf8 encrypt.py || goto :err
echo [3/3] GitHub 배포
git add docs && git commit -m "site: %date% %time%" && git push
echo 완료. 1~2분 뒤 GitHub Pages 링크에 반영됩니다.
goto :eof
:err
echo 실패 — 위 메시지를 확인하세요.
exit /b 1
