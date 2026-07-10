# Hodimlar tizimi — barcha xizmatlarni ishga tushirish (API, bot, scheduler, sayt).
# Har bir xizmat allaqachon ishlayotgan bo'lsa, qayta ishga tushirilmaydi (dublikat oldini olish).
# Loglar: logs\ papkasida. Windows Task Scheduler logon'da shu skriptni yashirin oynada chaqiradi.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

function Test-PortBusy([int]$port) {
    try { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Out-Null; $true } catch { $false }
}

function Test-PyModuleRunning([string]$pattern) {
    $found = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match $pattern }
    [bool]$found
}

function Start-Hidden([string]$exe, [string]$exeArgs, [string]$workDir, [string]$logName) {
    Start-Process -FilePath $exe -ArgumentList $exeArgs -WorkingDirectory $workDir -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "$logName.log") `
        -RedirectStandardError (Join-Path $logs "$logName.err.log")
}

# 1) API (port 8000)
if (-not (Test-PortBusy 8000)) {
    Start-Hidden $py "-m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level warning" $root "api"
    "API ishga tushirildi"
} else { "API allaqachon ishlayapti (port 8000)" }

# 2) Telegram bot
if (-not (Test-PyModuleRunning "bot\.main")) {
    Start-Hidden $py "-m bot.main" $root "bot"
    "Bot ishga tushirildi"
} else { "Bot allaqachon ishlayapti" }

# 3) Scheduler (eslatmalar, kunlik xulosa, CRM sync, oylik bonus)
if (-not (Test-PyModuleRunning "scheduler\.main")) {
    Start-Hidden $py "-m scheduler.main" $root "scheduler"
    "Scheduler ishga tushirildi"
} else { "Scheduler allaqachon ishlayapti" }

# 4) Sayt (Vite dev server, port 5173)
if (-not (Test-PortBusy 5173)) {
    Start-Hidden "cmd.exe" "/c npm run dev" (Join-Path $root "web") "web"
    "Sayt ishga tushirildi"
} else { "Sayt allaqachon ishlayapti (port 5173)" }
