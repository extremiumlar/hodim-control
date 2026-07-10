# Hodimlar tizimi — barcha xizmatlarni to'xtatish.

$stopped = @()

# API va sayt — port bo'yicha
foreach ($port in 8000, 5173) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
        foreach ($c in $conns) {
            Stop-Process -Id $c.OwningProcess -Force -Confirm:$false -ErrorAction SilentlyContinue
            $stopped += "port ${port} (PID $($c.OwningProcess))"
        }
    } catch {}
}

# Bot va scheduler — buyruq qatori bo'yicha
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match "bot\.main|scheduler\.main" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue
        $stopped += "PID $($_.ProcessId)"
    }

if ($stopped) { "To'xtatildi: $($stopped -join ', ')" } else { "Ishlayotgan xizmat topilmadi" }
