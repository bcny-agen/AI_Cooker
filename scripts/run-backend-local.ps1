[CmdletBinding()]
param(
    [string]$EnvFile,
    [switch]$ValidateOnly,
    [switch]$SkipConnectivityChecks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $PSScriptRoot '..\backend\.env.local'
}

$backendDirectory = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '..\backend')
)
$resolvedEnvFile = [System.IO.Path]::GetFullPath($EnvFile)

function Test-PlaceholderValue {
    param([string]$Value)

    return [string]::IsNullOrWhiteSpace($Value) `
        -or $Value -match '^(replace-with-|your-|<.+>)'
}

function Import-LocalEnvironment {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Local backend configuration is missing. Copy backend/.env.local.example to backend/.env.local and fill it manually."
    }

    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $lineNumber++
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }

        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) {
            throw "Invalid backend/.env.local syntax at line $lineNumber. Expected NAME=VALUE."
        }

        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim()
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
            throw "Invalid environment variable name at line $lineNumber."
        }
        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') `
                    -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        [System.Environment]::SetEnvironmentVariable(
            $name,
            $value,
            [System.EnvironmentVariableTarget]::Process
        )
    }
}

function Assert-RequiredConfiguration {
    $requiredNames = @(
        'DB_URL',
        'DB_USERNAME',
        'DB_PASSWORD',
        'JWT_SECRET',
        'ALIYUN_OSS_ENDPOINT',
        'ALIYUN_OSS_REGION',
        'ALIYUN_OSS_BUCKET_NAME',
        'ALIYUN_OSS_ACCESS_KEY_ID',
        'ALIYUN_OSS_ACCESS_KEY_SECRET',
        'AI_COOKER_BASE_URL',
        'CORS_ALLOWED_ORIGINS'
    )

    $missingNames = @()
    foreach ($name in $requiredNames) {
        $value = [System.Environment]::GetEnvironmentVariable($name, 'Process')
        if (Test-PlaceholderValue -Value $value) {
            $missingNames += $name
        }
    }
    if ($missingNames.Count -gt 0) {
        throw "Required local backend values are missing or still placeholders: $($missingNames -join ', '). No secret values were displayed."
    }

    $jwtSecret = [System.Environment]::GetEnvironmentVariable('JWT_SECRET', 'Process')
    if ([System.Text.Encoding]::UTF8.GetByteCount($jwtSecret) -lt 32) {
        throw 'JWT_SECRET must contain at least 32 UTF-8 bytes.'
    }

    $databaseUrl = [System.Environment]::GetEnvironmentVariable('DB_URL', 'Process')
    if (-not $databaseUrl.StartsWith('jdbc:mysql://', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'DB_URL must be a JDBC MySQL URL beginning with jdbc:mysql://.'
    }

    $ossEndpointText = [System.Environment]::GetEnvironmentVariable('ALIYUN_OSS_ENDPOINT', 'Process')
    $ossEndpoint = $null
    if (-not [System.Uri]::TryCreate(
            $ossEndpointText,
            [System.UriKind]::Absolute,
            [ref]$ossEndpoint
        ) -or $ossEndpoint.Scheme -ne 'https' -or -not $ossEndpoint.Host) {
        throw 'ALIYUN_OSS_ENDPOINT must be an absolute HTTPS URL.'
    }
    if (($ossEndpoint.AbsolutePath -and $ossEndpoint.AbsolutePath -ne '/') `
            -or $ossEndpoint.Query `
            -or $ossEndpoint.Fragment) {
        throw 'ALIYUN_OSS_ENDPOINT must be an HTTPS origin without a path, query string, or fragment.'
    }

    $ossRegion = [System.Environment]::GetEnvironmentVariable('ALIYUN_OSS_REGION', 'Process')
    if ($ossEndpoint.Host.EndsWith('.aliyuncs.com') `
            -and -not $ossEndpoint.Host.Contains($ossRegion)) {
        Write-Warning 'The OSS endpoint hostname does not include ALIYUN_OSS_REGION. Verify endpoint and region consistency before uploading.'
    }

    $aiBaseUrlText = [System.Environment]::GetEnvironmentVariable('AI_COOKER_BASE_URL', 'Process')
    $aiBaseUrl = $null
    if (-not [System.Uri]::TryCreate(
            $aiBaseUrlText,
            [System.UriKind]::Absolute,
            [ref]$aiBaseUrl
        ) -or $aiBaseUrl.Scheme -notin @('http', 'https')) {
        throw 'AI_COOKER_BASE_URL must be an absolute HTTP(S) URL.'
    }

    $corsOrigins = [System.Environment]::GetEnvironmentVariable(
        'CORS_ALLOWED_ORIGINS',
        'Process'
    ).Split(',', [System.StringSplitOptions]::RemoveEmptyEntries)
    if ($corsOrigins.Count -eq 0) {
        throw 'CORS_ALLOWED_ORIGINS must contain at least one origin.'
    }
    foreach ($originText in $corsOrigins) {
        $origin = $null
        if (-not [System.Uri]::TryCreate(
                $originText.Trim(),
                [System.UriKind]::Absolute,
                [ref]$origin
            ) -or $origin.Scheme -notin @('http', 'https') `
                -or -not $origin.Host `
                -or ($origin.AbsolutePath -and $origin.AbsolutePath -ne '/')) {
            throw 'Every CORS_ALLOWED_ORIGINS entry must be an absolute HTTP(S) origin without a path.'
        }
    }
}

function Assert-PythonServiceAvailable {
    $baseUrl = [System.Environment]::GetEnvironmentVariable(
        'AI_COOKER_BASE_URL',
        'Process'
    ).TrimEnd('/')
    try {
        $response = Invoke-RestMethod `
            -Method Get `
            -Uri "$baseUrl/api/v1/health" `
            -TimeoutSec 5
        if ($response.status -ne 'ok') {
            throw 'Unexpected health response.'
        }
    } catch {
        throw "Python AI service is unavailable at AI_COOKER_BASE_URL. Start FastAPI first. Internal details: $($_.Exception.Message)"
    }
}

try {
    Import-LocalEnvironment -Path $resolvedEnvFile
    Assert-RequiredConfiguration

    if (-not $SkipConnectivityChecks) {
        Assert-PythonServiceAvailable
    }

    Write-Host 'Local backend configuration validation passed. Secret values were not displayed.'
    if ($ValidateOnly) {
        exit 0
    }

    if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) {
        throw 'Maven was not found on PATH.'
    }

    Push-Location $backendDirectory
    try {
        & mvn spring-boot:run
        if ($LASTEXITCODE -ne 0) {
            throw "Spring Boot exited with code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} catch {
    Write-Host "Backend startup blocked: $($_.Exception.Message)" `
        -ForegroundColor Red
    exit 1
}
