# Piano

Full-screen live view of the desktop stream, plus saved microphone clips.

Start the backend, then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

This page is password protected. Set `APP_PASSWORD` in `backend/.env` (see
`backend/.env.example`) — the page will prompt for it and verify it against
the backend on load.

To serve this folder on its own (backend still on 8000):

```bash
cd frontend
python -m http.server 5173
```
