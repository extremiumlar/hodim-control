# Hodimlar tizimi — barcha xizmatlarni ishga tushirish (API, bot, scheduler, sayt).
# Har bir xizmat allaqachon ishlayotgan bo'lsa, qayta ishga tushirilmaydi (dublikat oldini olish).
# Loglar: logs\ papkasida. Windows Task Scheduler logon'da shu skriptni yashirin oynada chaqiradi.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

# O'z jurnali — Task Scheduler yashirin oynada chaqirganda stdout yo'qoladi,
# shu fayldan skript nima qilganini ko'rish mumkin.
$selfLog = Join-Path $logs "start_all.log"
"=== start_all $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $selfLog -Encoding utf8
function Log([string]$msg) {
    $msg
    "$(Get-Date -Format 'HH:mm:ss') $msg" | Out-File $selfLog -Append -Encoding utf8
}

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
    Log "API ishga tushirildi"
} else { Log "API allaqachon ishlayapti (port 8000)" }

# 2) Telegram bot
if (-not (Test-PyModuleRunning "bot\.main")) {
    Start-Hidden $py "-m bot.main" $root "bot"
    Log "Bot ishga tushirildi"
} else { Log "Bot allaqachon ishlayapti" }

# 3) Scheduler (eslatmalar, kunlik xulosa, CRM sync, oylik bonus)
if (-not (Test-PyModuleRunning "scheduler\.main")) {
    Start-Hidden $py "-m scheduler.main" $root "scheduler"
    Log "Scheduler ishga tushirildi"
} else { Log "Scheduler allaqachon ishlayapti" }

# 4) Sayt (Vite dev server, port 5173)
if (-not (Test-PortBusy 5173)) {
    Start-Hidden "cmd.exe" "/c npm run dev" (Join-Path $root "web") "web"
    Log "Sayt ishga tushirildi"
} else { Log "Sayt allaqachon ishlayapti (port 5173)" }

# Manzillar — cmd oynasida (va start_all.log da) ko'rinadi
Log ""
Log "Manzillar:"
Log "  API (backend):        http://localhost:8000"
Log "  Sayt (shu kompyuter): https://localhost:5173"
# Faqat FAOL (Preferred) manzillar — Deprecated/Tentative (eski Wi-Fi, APIPA)
# ko'rsatilsa foydalanuvchi o'lik manzilga kirib "sayt ishlamayapti" deb o'ylaydi.
Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { Log "  Sayt (telefon/tarmoq): https://$($_.IPAddress):5173" }
Log "  (telefonda birinchi ochishda sertifikat ogohlantirishida 'Advanced -> Proceed' bosiladi)"

Log "tugadi"

# verifix (hodim_crm) yagona backendga birlashtirildi (2026-07-14): davomat endi
# FastAPI + asosiy panel ichida (/check-in, /attendance). Alohida Django/Next
# xizmatlari endi ishga tushirilmaydi; verifix/ papkasi arxiv sifatida qoladi.
