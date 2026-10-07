# Geplande taak (2u15 en 10u15): herschrijft het nieuws lokaal met Ollama en zet het resultaat op GitHub.
# Werkt in een eigen kopie van de repository, los van de map waarin we ontwikkelen.
# Logboek: %LOCALAPPDATA%\txtinfo\rewrite.log
$base = Join-Path $env:LOCALAPPDATA 'txtinfo'
$repo = Join-Path $base 'repo'
$log  = Join-Path $base 'rewrite.log'
New-Item -ItemType Directory -Force $base | Out-Null
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Out-File $log -Append -Encoding utf8 }

Log '==== start'
if (-not (Test-Path (Join-Path $repo '.git'))) {
    git clone -b dev https://github.com/Thibauddec/txt.info.git $repo 2>&1 | Out-File $log -Append -Encoding utf8
}
Set-Location $repo
git checkout -q dev 2>&1 | Out-File $log -Append -Encoding utf8
git pull -q --rebase 2>&1 | Out-File $log -Append -Encoding utf8

# Ollama moet draaien
try { Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 5 | Out-Null }
catch { Log 'Ollama starten'; Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden; Start-Sleep -Seconds 15 }

py -I rewrite.py 2>&1 | Out-File $log -Append -Encoding utf8

git add rewrites.json
git -c user.name='Thibauddec' -c user.email='decaluwe_thibaud@hotmail.com' commit -q -m "Herschreven berichten $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Out-File $log -Append -Encoding utf8
git pull -q --rebase 2>&1 | Out-File $log -Append -Encoding utf8
git push -q 2>&1 | Out-File $log -Append -Encoding utf8
Log '==== klaar'
