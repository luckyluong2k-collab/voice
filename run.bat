@echo off
chcp 65001 >nul
title Viet Voice Studio - Clone & TTS Tieng Viet 1-Click
color 0b

echo ====================================================================
echo               VIET VOICE STUDIO - 1-CLICK LAUNCHER
echo      Cong cu doc van ban & nhan ban giong noi Tieng Viet
echo ====================================================================
echo.

cd /d "%~dp0"

echo [1/3] Kiem tra moi truong Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Loi] Khong tim thay Python! Vui long cai dat Python truoc khi chay.
    pause
    exit /b 1
)

echo [2/3] Kiem tra thu vien phu thuoc...
python -c "import fastapi, uvicorn, edge_tts, aiofiles, imageio_ffmpeg" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Thong bao] Dang cai dat cac thu vien can thiet, vui long cho 1 phut...
    python -m pip install -r requirements.txt
)

echo [3/3] Khoi dong giao dien Web...
start "" "http://127.0.0.1:7860"

echo.
echo ====================================================================
echo   Tool dang chay tai dia chi: http://127.0.0.1:7860
echo   (Trinh duyet cua ban se tu dong mo len trong giay lat)
echo   De dung tool, hay dong cua so nay hoac an to hop phim Ctrl + C.
echo ====================================================================
echo.

python app.py

pause
