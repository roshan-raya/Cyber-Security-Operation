"""Load repo-root `.env` into os.environ (simple KEY=VALUE parser; does not require python-dotenv)."""
import os


def load_repo_dotenv():
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, rest = line.partition("=")
            key = key.strip()
            if not key:
                continue
            val = rest.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            os.environ[key] = val
