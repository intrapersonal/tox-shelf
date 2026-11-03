$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repo = 'intrapersonal/tox-shelf'
$dir = Join-Path $env:LOCALAPPDATA 'tox-shelf\bin'
$exe = Join-Path $dir 'shelf.exe'

New-Item -ItemType Directory -Force -Path $dir | Out-Null

Write-Host 'grabbing shelf.exe...'
try {
    Invoke-WebRequest "https://github.com/$repo/releases/latest/download/shelf.exe" -OutFile "$exe.part" -UseBasicParsing
    Move-Item -Force "$exe.part" $exe
} catch {
    Remove-Item -Force "$exe.part" -ErrorAction SilentlyContinue
    Write-Host "couldn't download it ($($_.Exception.Message))" -ForegroundColor Red
    Write-Host "if you have python you can do: py -m pip install git+https://github.com/$repo"
    exit 1
}

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$parts = @()
if ($userPath) { $parts = $userPath -split ';' | Where-Object { $_ } }
if ($parts -notcontains $dir) {
    [Environment]::SetEnvironmentVariable('Path', (($parts + $dir) -join ';'), 'User')
    Write-Host "added $dir to your PATH (new terminals will see it)"
}
$env:Path = "$env:Path;$dir"

& $exe --version
Write-Host ''
Write-Host 'done. try:' -ForegroundColor Green
Write-Host '  shelf search'
Write-Host '  shelf install wintd'
Write-Host '  shelf td        (sets up the shelf COMP inside touchdesigner)'
