import argparse

from app.runtime import Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("document_id")
    args = parser.parse_args()
    runtime = Runtime()
    try:
        token = runtime.identity.login(
            runtime.settings.admin_username, runtime.settings.admin_password.get_secret_value()
        )
        result = runtime.documents.reindex(runtime.identity.resolve(token), args.document_id)
        runtime.dispatch(result["task_id"])
        print("Created replacement index version, task:", result["task_id"])
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
