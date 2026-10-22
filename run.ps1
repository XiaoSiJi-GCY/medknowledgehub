param([ValidateSet("api", "ui", "worker", "infra", "init", "seed", "test")][string]$Mode = "api")
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
switch ($Mode) {
 "infra" { docker compose up -d postgres redis neo4j milvus }
 "api" { & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 }
 "ui" { & $python -m streamlit run ui/streamlit_app.py --server.address 127.0.0.1 --server.port 8510 }
 "worker" { & $python -m celery -A app.workers.celery_app:celery_app worker --pool=solo --loglevel=INFO }
 "init" { & $python -m scripts.bootstrap }
 "seed" { & $python -m scripts.import_corpus }
 "test" { & $python -m pytest -q }
}
