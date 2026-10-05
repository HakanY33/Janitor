# Janitor kayitcisi - PC yedegi (docs/SERVER.md "PC yedek plani").
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pc_kayit.ps1 -Kayitci trades
# Kayitci cikarsa (ag, hata, kill) 30 sn sonra yeniden baslatir; her cikis loga yazilir.
# 40 sembol: liquidity.json ilk 20 + liquidity_soguk.json ilk 20 (sunucudaki listeler).
# -Kok: veri koku (JANITOR_DATA_ROOT). Sunucuyla paralel kayitta ayri kok (ornek: goc\pc\data),
# birlestirmeden sonra varsayilan data.
param(
    [Parameter(Mandatory)][ValidateSet("trades", "spread")][string]$Kayitci,
    [string]$Python = (Get-Command python).Source,
    [string]$Kok = "data"
)
Set-Location (Join-Path $PSScriptRoot "..")
$env:JANITOR_DATA_ROOT = $Kok
$s = @((Get-Content data\bingx\liquidity.json -Raw | ConvertFrom-Json).symbols[0..19]) +
     @((Get-Content data\bingx\liquidity_soguk.json -Raw | ConvertFrom-Json).symbols[0..19])
New-Item -ItemType Directory -Force logs | Out-Null
while ($true) {
    $log = "logs\pc-$Kayitci-$((Get-Date).ToUniversalTime().ToString('yyyyMMdd')).log"
    cmd /c "`"$Python`" -u -m scripts.${Kayitci}_logger --symbols $($s -join ' ') >> $log 2>&1"
    "$((Get-Date).ToUniversalTime().ToString('s'))Z cikti (kod $LASTEXITCODE), 30 sn sonra yeniden" |
        Add-Content $log
    Start-Sleep 30
}
