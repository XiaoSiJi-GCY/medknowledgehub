"""Managed local processes; each project keeps its own virtual environment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import time
import httpx
import psutil
from dotenv import dotenv_values
ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
RUNTIME = ROOT / ".runtime"
CONFIG = Path(os.getenv("CARE_SUITE_ENV_FILE", ROOT / ".env"))
PROCESSES = {
 "medhub-api": ("medknowledgehub", ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"], "http://127.0.0.1:8010/health"),
 "medhub-worker": ("medknowledgehub", ["-m", "celery", "-A", "app.workers.celery_app:celery_app", "worker", "--pool=solo", "--loglevel=INFO", "--hostname=medhub-suite@%h"], None),
 "carepilot-api": ("carepilot", ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], "http://127.0.0.1:8000/health"),
 "carepilot-ui": ("carepilot", ["-m", "streamlit", "run", "ui/streamlit_app.py", "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=true"], "http://127.0.0.1:8501/_stcore/health"),
 "medhub-ui": ("medknowledgehub", ["-m", "streamlit", "run", "ui/streamlit_app.py", "--server.address=127.0.0.1", "--server.port=8510", "--server.headless=true"], "http://127.0.0.1:8510/_stcore/health"),
}


def python(project):
    path = BASE / project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not path.exists():
        raise RuntimeError(f"Missing interpreter: {path}")
    return str(path)


def environment():
    env = dict(os.environ)
    env.update(CARE_SUITE_ENV_FILE=str(CONFIG), PYTHONIOENCODING="utf-8")
    return env


def command(project, args):
    subprocess.run([python(project), *args], cwd=BASE / project, env=environment(), check=True)


def healthy(url):
    try:
        return httpx.get(url, timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def record(name):
    try:
        value = json.loads((RUNTIME / (name + ".json")).read_text())
        proc = psutil.Process(value["pid"])
        if abs(proc.create_time() - value["created"]) < 0.01 and proc.is_running():
            return proc
    except (OSError, ValueError, psutil.Error):
        pass
    return None


def start_one(name):
    project, args, url = PROCESSES[name]
    if record(name):
        print(name, "already managed", flush=True)
        return
    if url and healthy(url):
        raise RuntimeError(f"{name}: port is used by an unmanaged process. Stop it first.")
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / (name + ".log")).open("ab") as output:
        child = subprocess.Popen([python(project), *args], cwd=BASE / project, env=environment(), stdout=output,
                                 stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    proc = psutil.Process(child.pid)
    (RUNTIME / (name + ".json")).write_text(json.dumps({"pid": child.pid, "created": proc.create_time()}))
    for attempt in range(60):
        if child.poll() is not None:
            raise RuntimeError(f"{name} exited. See .runtime/{name}.log")
        if (url and healthy(url)) or (not url and attempt >= 5):
            print(name, "started", flush=True)
            return
        time.sleep(1)
    raise RuntimeError(f"{name} did not become ready. See .runtime/{name}.log")


def infra():
    ready = True
    for port in (15432, 16379, 17687, 19531):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass
        except OSError:
            ready = False
    if ready:
        print("Existing infrastructure is reachable; preserved.", flush=True)
        return
    subprocess.run(["docker", "compose", "up", "-d", "postgres", "redis", "neo4j", "milvus"], cwd=BASE / "medknowledgehub", check=True)


def supervisor_state():
    try:
        state = json.loads((RUNTIME / "supervisor-status.json").read_text())
        return state if time.time() - state["updated"] < 12 else None
    except (OSError, ValueError, KeyError):
        return None


def heartbeat():
    state = {"updated": time.time(), "processes": {name: bool(record(name)) for name in PROCESSES}}
    temporary = RUNTIME / "supervisor-status.tmp"
    temporary.write_text(json.dumps(state))
    temporary.replace(RUNTIME / "supervisor-status.json")


def status():
    state = supervisor_state()
    for name, (_, _, url) in PROCESSES.items():
        print(name, "ready" if url and healthy(url) else "running" if (state and state["processes"].get(name)) or record(name) else "stopped")
    if healthy("http://127.0.0.1:8010/health"):
        token = dotenv_values(CONFIG).get("SERVICE_TOKEN", "")
        try:
            r = httpx.get("http://127.0.0.1:8010/api/v1/auth/me", headers={"Authorization": "Bearer " + token}, timeout=5)
            print("knowledge service identity", "ready (read only)" if r.status_code == 200 and r.json().get("role") == "viewer" else "unavailable")
        except (httpx.HTTPError, ValueError):
            print("knowledge service identity unavailable")


def stop_processes():
    for name in reversed(PROCESSES):
        proc = record(name)
        if proc:
            try:
                children = proc.children(recursive=True)
                for child in reversed(children):
                    child.terminate()
                proc.terminate()
                _, alive = psutil.wait_procs([proc, *children], timeout=5)
                for item in alive:
                    item.kill()
            except psutil.Error:
                pass
            print(name, "stopped")
    print("Database containers and persistent data were preserved.")


def stop():
    if supervisor_state():
        (RUNTIME / "stop.request").touch()
        for _ in range(20):
            if not supervisor_state():
                print("Managed applications stopped; database containers preserved.")
                return
            time.sleep(1)
        raise RuntimeError("Supervisor did not acknowledge stop; check .runtime/supervisor.log")
    stop_processes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "serve", "stop", "status", "init", "seed", "test", "smoke"])
    action = parser.parse_args().action
    if action == "init":
        from configure import configure
        configure()
        infra()
        command("medknowledgehub", ["-m", "scripts.bootstrap"])
    elif action in {"start", "serve"}:
        if not CONFIG.exists():
            raise RuntimeError("Run configure.py or run.ps1 init first.")
        if supervisor_state():
            status()
            return
        infra()
        RUNTIME.mkdir(exist_ok=True)
        if action == "start":
            with (RUNTIME / "supervisor.log").open("ab") as output:
                child = subprocess.Popen([sys.executable, str(ROOT / "suite.py"), "serve"], cwd=ROOT,
                                         env=environment(), stdout=output, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            for _ in range(120):
                if supervisor_state():
                    status()
                    return
                if child.poll() is not None:
                    raise RuntimeError("Supervisor exited; check .runtime/supervisor.log")
                time.sleep(1)
            raise RuntimeError("Startup timed out; check .runtime/supervisor.log")
        (RUNTIME / "stop.request").unlink(missing_ok=True)
        try:
            for name in PROCESSES:
                start_one(name)
            heartbeat()
            status()
            print("Supervisor active; applications run in the background.", flush=True)
            while any(record(name) for name in PROCESSES):
                if (RUNTIME / "stop.request").exists():
                    break
                heartbeat()
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            stop_processes()
            (RUNTIME / "supervisor-status.json").unlink(missing_ok=True)
            (RUNTIME / "stop.request").unlink(missing_ok=True)
    elif action == "stop": stop()
    elif action == "status": status()
    elif action == "seed": command("medknowledgehub", ["-m", "scripts.import_corpus", "--wait"])
    elif action == "test":
        for project in ("carepilot", "medknowledgehub"):
            command(project, ["-m", "pytest", "-q"])
        subprocess.run([sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q"], cwd=ROOT, check=True)
    else:
        subprocess.run([sys.executable, str(ROOT / "smoke_live.py")], cwd=ROOT, env=environment(), check=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
