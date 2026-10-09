@echo off
chcp 65001 >nul
cd /d %~dp0
set PY=..\GenuoneMonitor_DevPackage\.venv\Scripts\python.exe
echo [1/2] 모니터 서버(localhost:5001)에서 화면 데이터 수집 → 봉인  (옵션: publish.bat --quick ^| --fresh)
"%PY%" -X utf8 build_static.py %1 || goto :err
echo [2/2] GitHub 배포
git add -A docs && git commit -m "site: %date% %time%" && git push
echo 완료. 1~2분 뒤 https://daeyeongmun.github.io/gns-monitor-site/ 에 반영됩니다.
goto :eof
:err
echo 실패 — 모니터 서버가 켜져 있는지 확인하세요 (GenuoneMonitor_DevPackage\app.py).
exit /b 1
