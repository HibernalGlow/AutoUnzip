# PowerShell helper: run ugrep with NUL-separated output and resolve paths to absolute
param(
    [string]$Pattern = 'avif',
    [string]$Include = '*.zip',
    [string]$Base = '.'
)

# Build argument array to avoid quoting problems
$args = @('-0','-L','-r','-i','--include=' + $Include, $Pattern, $Base)

# Use Start-Process to capture output without complex quoting
$proc = Start-Process -FilePath 'ugrep' -ArgumentList $args -NoNewWindow -RedirectStandardOutput -RedirectStandardError -PassThru
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

if ($stderr -and $stderr.Trim()) {
    Write-Error $stderr.Trim()
}

if ($stdout -and $stdout.Length -gt 0) {
    $parts = $stdout -split "\0"
    foreach ($p in $parts) {
        if ([string]::IsNullOrEmpty($p)) { continue }
        try {
            $rp = Resolve-Path -LiteralPath $p -ErrorAction Stop
            $rp | ForEach-Object { Write-Output $_.Path }
        } catch {
            Write-Warning "无法解析路径: $p -- $($_.Exception.Message)"
        }
    }
}
