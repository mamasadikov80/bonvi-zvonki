# ══════════════════════════════════════════════════════════════
#  BonviZvonki — ishga tushirish (Windows PowerShell)
#
#  Bu skript README boshidagi buyruqning aynan o'zini bajaradi:
#      copy .env.example .env ; docker compose up -d --build
#
#  Skriptsiz ham bo'ladi — o'sha buyruqni qo'lda yozsangiz kifoya.
#  Yangilashda avval kodni torting:  git pull ; .\start.ps1
#
#  Ishga tushmasa (ExecutionPolicy):
#      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# ══════════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (Test-Path ".env") {
    Write-Host "  .env allaqachon bor - tegilmadi"
} else {
    Copy-Item ".env.example" ".env" -NoClobber
    Write-Host "  .env yaratildi (.env.example dan)"
}

docker compose up -d --build

Write-Host ""
Write-Host "  Konteynerlar ko'tarildi"
Write-Host "  ---------------------------------------------"
Write-Host "  Birinchi safar backend bazani tayyorlaydi - bu bir necha"
Write-Host "  daqiqa oladi. Holat:  docker compose ps"
Write-Host ""
Write-Host "  Dashboard   ->  http://localhost:5180"
Write-Host "  API hujjat  ->  http://localhost:8010/docs"
Write-Host ""
Write-Host "  Kirish:  admin@zvonki.uz  /  admin12345"
Write-Host "  Loglar:  docker compose logs -f backend"
Write-Host ""
