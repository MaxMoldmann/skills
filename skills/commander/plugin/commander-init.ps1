param()
$base = "$env:USERPROFILE\.commander"
$missing = @()

$defaults = @(
    [pscustomobject]@{ path = "$base\config.json";                    content = '{"speak":{"enabled":false,"voice":"am_adam"}}' }
    [pscustomobject]@{ path = "$base\memory\rules.json";               content = '{"rules":[]}' }
    [pscustomobject]@{ path = "$base\memory\response-templates.json";  content = '{"templates":[]}' }
    [pscustomobject]@{ path = "$base\data\pending-blocks.json";        content = '{"version":1,"next_id":1,"next_order":1,"records":[]}' }
    [pscustomobject]@{ path = "$base\data\blocked-commands.json";      content = '{"version":1,"records":[]}' }
)

foreach ($d in $defaults) {
    if (-not (Test-Path $d.path)) {
        $d.content | Set-Content $d.path -Encoding UTF8
        $missing += (Split-Path $d.path -Leaf)
    }
}

$srPath = "$env:USERPROFILE\.claude\commands\status-report.md"
if (-not (Test-Path $srPath)) { $missing += 'status-report.md (create from /status-report section in SKILL.md)' }

$statsPath = "$base\scripts\commander-stats.ps1"
if (-not (Test-Path $statsPath)) { $missing += 'commander-stats.ps1 (copy from plugin dir)' }

$writePath = "$base\scripts\commander-write.ps1"
if (-not (Test-Path $writePath)) { $missing += 'commander-write.ps1 (copy from plugin dir)' }

$configJson = Get-Content "$base\config.json" -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
if ($configJson.speak.enabled) {
    $speakPy = "$env:USERPROFILE\.claude\skills\speak\speak.py"
    if (-not (Test-Path $speakPy)) { $missing += 'WARN: speak.enabled=true but speak.py missing' }
}

if ($missing.Count -gt 0) { Write-Output "missing: $($missing -join '; ')" }
else { Write-Output 'ok' }
