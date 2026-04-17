# OneRadar API

FastAPI backend skeleton for OneRadar V1.

## Run

```bash
cd E:\OneRadar\apps\api
uvicorn app.main:app --reload
```

## Endpoints

- `GET /api/health`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/items/import`
- `GET /api/items`
- `GET /api/items/{id}`
- `POST /api/items/{id}/reprocess`
- `GET /api/providers`
- `POST /api/providers`
- `PUT /api/providers/{id}`
- `DELETE /api/providers/{id}`
- `POST /api/providers/{id}/test`
- `GET /api/tasks`
- `GET /api/tasks/{id}`
- `POST /api/tasks/{id}/retry`

## Notes

This is a skeleton only. The routes return placeholder data and define the API shape that the worker and desktop client will consume.
