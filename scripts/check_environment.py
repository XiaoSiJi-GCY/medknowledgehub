import json

from fastapi.testclient import TestClient

from app.main import app


def main():
    with TestClient(app) as client:
        response = client.get("/health/ready")
        print(json.dumps(response.json(), ensure_ascii=False))
        raise SystemExit(0 if response.status_code == 200 else 1)


if __name__ == "__main__":
    main()
