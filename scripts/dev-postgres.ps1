<#
.SYNOPSIS
    Manage an isolated local PostgreSQL cluster for development.

.DESCRIPTION
    For machines without Docker. Creates a cluster in .pgdata using the
    installed PostgreSQL binaries (pgvector must be present in that
    installation), listens on a non-default port and uses the password in .env
    so the connection string matches production-style config.

.EXAMPLE
    powershell -File scripts/dev-postgres.ps1 init
    powershell -File scripts/dev-postgres.ps1 start
    powershell -File scripts/dev-postgres.ps1 migrate
    powershell -File scripts/dev-postgres.ps1 stop
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "start", "stop", "status", "migrate", "reset")]
    [string]$Action = "status",
    [string]$DataDir = ".pgdata",
    [int]$Port = 5544,
    [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin",
    [string]$Database = "abode",
    [string]$User = "abode"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Get-EnvValue([string]$Key) {
    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path $envPath)) { throw ".env not found; copy .env.example first" }
    foreach ($line in Get-Content $envPath) {
        if ($line -match "^\s*$Key\s*=\s*(.+)$") { return $Matches[1].Trim() }
    }
    throw "$Key missing from .env"
}

function Invoke-Psql([string]$Sql, [string]$Db = "postgres") {
    $env:PGPASSWORD = Get-EnvValue "POSTGRES_PASSWORD"
    try {
        & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U $User -d $Db -v ON_ERROR_STOP=1 -q -c $Sql
        if ($LASTEXITCODE -ne 0) { throw "psql failed (exit $LASTEXITCODE)" }
    }
    finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    }
}

function Invoke-PsqlScalar([string]$Sql, [string]$Db = "postgres") {
    $env:PGPASSWORD = Get-EnvValue "POSTGRES_PASSWORD"
    try {
        $output = & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U $User -d $Db -tAc $Sql
        if ($LASTEXITCODE -ne 0) { throw "psql failed (exit $LASTEXITCODE)" }
        return ($output | Out-String).Trim()
    }
    finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    }
}

switch ($Action) {
    "init" {
        if (Test-Path $DataDir) { throw "$DataDir already exists; use 'reset' to recreate" }
        $pwFile = Join-Path $env:TEMP "abode-pg-init-$PID.txt"
        try {
            Set-Content -Path $pwFile -Value (Get-EnvValue "POSTGRES_PASSWORD") -NoNewline -Encoding ascii
            & (Join-Path $PgBin "initdb.exe") -D $DataDir -U $User --pwfile $pwFile `
                --auth-local=scram-sha-256 --auth-host=scram-sha-256 -E UTF8 --locale=C
            if ($LASTEXITCODE -ne 0) { throw "initdb failed (exit $LASTEXITCODE)" }
        }
        finally {
            Remove-Item $pwFile -ErrorAction SilentlyContinue
        }
        Write-Host "Cluster created in $DataDir (port $Port). Next: start"
    }

    "start" {
        if (-not (Test-Path $DataDir)) { throw "$DataDir not found; run init first" }
        & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -l (Join-Path $DataDir "server.log") -o "-p $Port" -w start
        if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed" }
        Write-Host "Listening on 127.0.0.1:$Port as $User"
    }

    "stop" {
        & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -m fast -w stop
    }

    "status" {
        & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir status
    }

    "migrate" {
        $exists = Invoke-PsqlScalar "SELECT 1 FROM pg_database WHERE datname = '$Database'"
        if (-not $exists) {
            Write-Host "creating database $Database"
            Invoke-Psql "CREATE DATABASE $Database"
        }
        $migrations = Get-ChildItem (Join-Path $repoRoot "ai-service/migrations") -Filter "00*.sql" |
            Sort-Object Name
        if (-not $migrations) { throw "no migrations found" }
        $env:PGPASSWORD = Get-EnvValue "POSTGRES_PASSWORD"
        try {
            foreach ($migration in $migrations) {
                Write-Host "applying $($migration.Name)"
                & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U $User -d $Database `
                    -v ON_ERROR_STOP=1 -q -f $migration.FullName
                if ($LASTEXITCODE -ne 0) { throw "migration $($migration.Name) failed" }
            }
        }
        finally {
            Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        }
        Invoke-Psql "SELECT extname, extversion FROM pg_extension ORDER BY 1;" $Database
    }

    "reset" {
        if (Test-Path $DataDir) {
            & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -m immediate stop 2>$null
            Start-Sleep -Seconds 2
            Remove-Item -Recurse -Force $DataDir
        }
        Write-Host "Removed $DataDir; run init to recreate"
    }
}
