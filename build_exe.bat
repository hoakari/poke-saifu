@echo off
chcp 65001 > nul
echo ===================================================
echo   Poke-Saifu (ポケモン採譜) - Windows EXE ビルド
echo ===================================================
echo.

echo [1/3] 依存関係の確認・インストール...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] 依存関係のインストールに失敗しました。
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] PyInstaller によるビルド開始...
pyinstaller --noconfirm Poke-Saifu.spec
if %errorlevel% neq 0 (
    echo [!] ビルド中にエラーが発生しました。
    pause
    exit /b %errorlevel%
)

echo.
echo [3/3] ビルド完了！
echo 出力フォルダ: dist\Poke-Saifu\Poke-Saifu.exe
echo.
pause
