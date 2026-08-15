# update.ps1 - pakt de nieuwste gedownloade zip, zet de bestanden op hun plek en pusht.
# Gebruik:  .\update.ps1              (uitpakken + tonen wat er verandert)
#           .\update.ps1 -Push        (ook committen en pushen)
#           .\update.ps1 -Draaien     (daarna het model lokaal herberekenen)

param(
    [switch]$Push,
    [switch]$Draaien,
    [string]$Bericht = "Bijwerken vanuit Claude-sessie"
)

$ErrorActionPreference = "Stop"
$Project = $PSScriptRoot
if (-not $Project) { $Project = (Get-Location).Path }

# 1. nieuwste zip zoeken, ongeacht (1)/(2)-achtervoegsel
$zip = Get-ChildItem -Path "$HOME\Downloads", $HOME -Filter "dividend-waardering*.zip" `
         -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending |
       Select-Object -First 1

if (-not $zip) {
    Write-Host "Geen dividend-waardering*.zip gevonden in Downloads of $HOME." -ForegroundColor Red
    exit 1
}
Write-Host "Gevonden: $($zip.Name)  ($([math]::Round($zip.Length/1KB)) kB, $($zip.LastWriteTime))" -ForegroundColor Cyan

# 2. uitpakken naar een tijdelijke map
$tmp = Join-Path $env:TEMP "dw-update"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive $zip.FullName -DestinationPath $tmp -Force

# de zip bevat een map dividend-waardering/; val terug op de root als die ontbreekt
$bron = Join-Path $tmp "dividend-waardering"
if (-not (Test-Path $bron)) { $bron = $tmp }

# 3. kopiëren, .git en de venv met rust laten
Copy-Item "$bron\*" $Project -Recurse -Force -Exclude ".git", ".venv"
Remove-Item $tmp -Recurse -Force

# 4. controleren of het echt de nieuwe versie is
Set-Location $Project
$checks = @{
    "beursfilter"     = "f-index"
    "statusfilter"    = "f-status"
    "inkoopschakelaar"= "s-bb"
    "updatedatum"     = "opgehaald"
    "logo"            = "logo.png"
}
$ok = $true
foreach ($k in $checks.Keys) {
    $gevonden = Select-String -Path index.html -Pattern $checks[$k] -Quiet
    if ($gevonden) { Write-Host "  [ok]  $k" -ForegroundColor Green }
    else { Write-Host "  [--]  $k ontbreekt" -ForegroundColor Yellow; $ok = $false }
}
if (-not $ok) {
    Write-Host "`nNiet alle onderdelen gevonden - dit lijkt een oudere zip." -ForegroundColor Yellow
}

# 5. optioneel het model lokaal herberekenen
if ($Draaien) {
    Write-Host "`nModel herberekenen..." -ForegroundColor Cyan
    python fetch.py; python agenda.py; python valuate.py; python build.py
}

# 6. wijzigingen tonen en eventueel pushen
Write-Host ""
git status --short
if ($Push) {
    git add .
    $iets = git diff --staged --name-only
    if ($iets) {
        git commit -m $Bericht
        git push
        Write-Host "`nGepusht. Netlify deployt automatisch." -ForegroundColor Green
    } else {
        Write-Host "`nNiets gewijzigd - er stond al een actuele versie." -ForegroundColor Cyan
    }
} else {
    Write-Host "`nNog niet gepusht. Draai '.\update.ps1 -Push' of push handmatig." -ForegroundColor Cyan
}
