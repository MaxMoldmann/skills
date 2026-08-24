$log = "$env:USERPROFILE\.commander\data\decisions-log.jsonl"
$cutoff = (Get-Date).AddDays(-30).ToUniversalTime().ToString("o")
$entries = Get-Content $log -ErrorAction SilentlyContinue |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.ts -ge $cutoff }
$commanderEntries = @($entries | Where-Object { $_.tab -eq "Commander" })
$fleetEntries = @($entries | Where-Object { $_.tab -ne "Commander" })
$auto      = ($fleetEntries | Where-Object { $_.auto }).Count
$escalated = ($fleetEntries | Where-Object { -not $_.auto }).Count
$commanderAuto = ($commanderEntries | Where-Object { $_.auto }).Count
$timeSavedApprovals = @($fleetEntries | Where-Object {
    $_.auto -and $_.rule_id -notlike "wake-*"
})
$timeSavedHours = ($timeSavedApprovals.Count * 12) / 3600
$byRule = $fleetEntries | Where-Object { $_.auto } | Group-Object rule_id |
    Sort-Object Count -Descending | Select-Object -First 5
$byTab  = $fleetEntries | Group-Object tab |
    Sort-Object Count -Descending | Select-Object -First 5
Write-Output "auto=$auto commander_auto=$commanderAuto escalated=$escalated"
Write-Output ("time_saved_hours={0:0.0}" -f $timeSavedHours)
$byRule | ForEach-Object { Write-Output "rule:$($_.Name)=$($_.Count)" }
$byTab  | ForEach-Object { Write-Output "tab:$($_.Name)=$($_.Count)" }
