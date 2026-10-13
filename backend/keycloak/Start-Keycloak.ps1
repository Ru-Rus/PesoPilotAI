# Run from any directory after downloading the local runtimes described in README.
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$javaFolder = Get-ChildItem -LiteralPath (Join-Path $repoRoot '.tools/java') -Directory | Select-Object -First 1
$serverFolder = Join-Path $repoRoot '.tools/keycloak/keycloak-26.7.5'
if (-not $javaFolder -or -not (Test-Path -LiteralPath (Join-Path $serverFolder 'bin/kc.bat'))) {
    throw 'Download workspace-local OpenJDK 21 and Keycloak 26.7.5 as described in README, or use Docker Compose.'
}
$env:JAVA_HOME = $javaFolder.FullName
# Credentials come from the ignored backend/.env, never from command-line arguments.
$config = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $repoRoot 'backend/.env')) {
    if ($line -match '^([A-Z_]+)=(.*)$') { $config[$matches[1]] = $matches[2] }
}
if (-not $config['KEYCLOAK_ADMIN_PASSWORD'] -or -not $config['OIDC_CLIENT_SECRET']) {
    throw 'Set KEYCLOAK_ADMIN_PASSWORD and OIDC_CLIENT_SECRET in backend/.env before starting.'
}
$env:KC_BOOTSTRAP_ADMIN_USERNAME = 'admin'
$env:KC_BOOTSTRAP_ADMIN_PASSWORD = $config['KEYCLOAK_ADMIN_PASSWORD']
$realm = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'realm.json') -Raw | ConvertFrom-Json
$realm.clients[0] | Add-Member -NotePropertyName secret -NotePropertyValue $config['OIDC_CLIENT_SECRET'] -Force
$importFolder = Join-Path $serverFolder 'data/import'
New-Item -ItemType Directory -Path $importFolder -Force | Out-Null
$realm | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $importFolder 'realm.json') -Encoding UTF8
& (Join-Path $serverFolder 'bin/kc.bat') start-dev --http-host=127.0.0.1 --hostname=http://localhost:8080 --import-realm
