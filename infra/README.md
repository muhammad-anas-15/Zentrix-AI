# infra/

- `Dockerfile`: backend image (FastAPI). Build: `docker build -f infra/Dockerfile backend`.
- `docker-compose.yml`: local stack (migrate -> api, postgres 16, redis 7). `docker compose -f infra/docker-compose.yml up --build`,
  then `curl http://127.0.0.1:8000/health`. Ports bind to localhost only.
- Secrets come from `backend/.env` (copy `backend/.env.example`); never bake them into the image.
- Model artifacts and the candle cache live in the `ml_data` volume (`/data`), not in the image or git.
- Phase 2 adds the worker service; Phase 6 adds CI, deployment and backup notes.
