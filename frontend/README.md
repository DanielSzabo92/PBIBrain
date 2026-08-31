# Brain Inspector

Run the UI:

```powershell
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Set `$env:BRAIN_API_URL` to use another local API address.

The local API must expose `GET /api/brain` and `POST /api/review`. The backend WSGI app is created with `backend.api.app.create_app`.
