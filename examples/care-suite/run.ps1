param([ValidateSet("start", "stop", "status", "init", "seed", "test", "smoke")][string]$Mode = "status")
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\medknowledgehub\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Create MedKnowledgeHub .venv first; see README.md." }
& $python (Join-Path $PSScriptRoot "suite.py") $Mode
exit $LASTEXITCODE
