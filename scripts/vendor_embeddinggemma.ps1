param(
  [string]$Source = "g:\Gemma3n-E2B\Rekenr\models--google--embeddinggemma-300m\snapshots\57c266a740f537b4dc058e1b0cda161fd15afa75",
  [string]$Dest = (Join-Path $PSScriptRoot "..\\assets\\models\\embeddinggemma-300m"),
  [switch]$Zip
)

$Dest = (Resolve-Path (New-Item -ItemType Directory -Force -Path $Dest)).Path

Write-Host "Copying model snapshot..."
Write-Host "  Source: $Source"
Write-Host "  Dest:   $Dest"

Copy-Item -Recurse -Force -Path (Join-Path $Source "*") -Destination $Dest

if ($Zip) {
  $zipPath = Join-Path (Split-Path $Dest -Parent) "embeddinggemma-300m.zip"
  if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
  Write-Host "Creating zip: $zipPath"
  $stage = Join-Path $env:TEMP ("embeddinggemma-300m-stage-" + [guid]::NewGuid().ToString("n"))
  New-Item -ItemType Directory -Force -Path $stage | Out-Null
  Copy-Item -Recurse -Force -Exclude ".gitignore" -Path (Join-Path $Dest "*") -Destination $stage
  Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath
  Remove-Item -Recurse -Force -Path $stage
  $hash = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLowerInvariant()
  Write-Host "SHA256: $hash"
}
