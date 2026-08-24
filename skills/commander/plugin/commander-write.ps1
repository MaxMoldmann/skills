param(
    [Parameter(Mandatory)][string]$Op,
    [string]$Id,
    [string]$Pat,
    [string]$Cwd,
    [double]$Conf = 0.9,
    [string]$Status,
    [string]$Rules,
    [string]$Tab,
    [string]$Cmd,
    [string]$Rule,
    [bool]$Auto = $false,
    [string]$Outcome = "approved"
)

$base = "$env:USERPROFILE\.commander"
$now  = (Get-Date).ToUniversalTime().ToString("o")

switch ($Op) {
    'add-rule' {
        $path = "$base\memory\rules.json"
        $data = Get-Content $path -Raw | ConvertFrom-Json
        $r = [pscustomobject]@{ id=$Id; cmd_pattern=$Pat; confidence=$Conf; use_count=0; last_used=$null }
        if ($Cwd) { $r | Add-Member -NotePropertyName cwd -NotePropertyValue $Cwd }
        $data.rules += $r
        $data | ConvertTo-Json -Depth 5 | Set-Content $path -Encoding UTF8
        Write-Output "rule-added:$Id"
    }
    'retire' {
        $path = "$base\data\pending-blocks.json"
        $data = Get-Content $path -Raw | ConvertFrom-Json
        $rec  = $data.records | Where-Object { $_.id -eq $Id }
        if (-not $rec) { Write-Output "not-found:$Id"; return }
        $rec.status = $Status
        $rec | Add-Member -Force -NotePropertyName resolved_at -NotePropertyValue $now
        $ruleArr = if ($Rules) { @($Rules -split ',') } else { @() }
        $rec | Add-Member -Force -NotePropertyName resolution -NotePropertyValue (
            [pscustomobject]@{ choice=$Status; rule_ids=$ruleArr; executed=$false }
        )
        $data | ConvertTo-Json -Depth 10 | Set-Content $path -Encoding UTF8
        Write-Output "retired:$Id"
    }
    'drop' {
        $path = "$base\data\pending-blocks.json"
        $data = Get-Content $path -Raw | ConvertFrom-Json
        $rec  = $data.records | Where-Object { $_.id -eq $Id }
        if (-not $rec) { Write-Output "not-found:$Id"; return }
        $rec.status = 'dropped'
        $rec | Add-Member -Force -NotePropertyName resolved_at -NotePropertyValue $now
        $rec | Add-Member -Force -NotePropertyName resolution -NotePropertyValue (
            [pscustomobject]@{ choice='drop_current' }
        )
        $data | ConvertTo-Json -Depth 10 | Set-Content $path -Encoding UTF8
        Write-Output "dropped:$Id"
    }
    'log' {
        $path = "$base\data\decisions-log.jsonl"
        [pscustomobject]@{ ts=$now; rule_id=$Rule; tab=$Tab; cmd=$Cmd; confidence=$Conf; auto=$Auto; outcome=$Outcome } |
            ConvertTo-Json -Compress | Add-Content $path -Encoding UTF8
        Write-Output "logged:$Rule"
    }
}
