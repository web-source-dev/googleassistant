# Piano Backend

Relays the voice-assistant desktop stream to the browser. Frames are not saved.
Spoken microphone clips are saved as WAV files and can be played on the live page.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # then set APP_PASSWORD to a real password
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Or `run.bat`.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Password protection

The web viewer (frontend) is locked behind a password. Set `APP_PASSWORD` in
`backend/.env` (copy `.env.example`) or in the environment before starting the
backend. The frontend prompts for the password, exchanges it for a bearer
token via `POST /api/auth/login`, and sends that token on every request. The
password never lives in frontend code. Tokens expire after 30 days.

## API

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/api/auth/login` | Exchange the password for a bearer token | — |
| GET | `/api/health` | Backend status | — |
| GET | `/api/live` | Current live session | required |
| GET | `/api/live/frame` | Latest JPEG | required |
| GET | `/api/joins` | Screen-share history | required |
| GET/POST | `/api/listen` | Voice assistant on/off | required |
| GET | `/api/audio` | List saved voice clips | required |
| GET | `/api/audio/{id}` | Download / play a WAV clip | required |
| POST | `/api/audio` | Upload a spoken clip from the desktop app | — |
| WS | `/ws/record` | Frames in from the desktop app | — |
| WS | `/ws/live` | Frames and new-clip events out to the web viewer | required (`?token=`) |

"required" routes accept the token as an `Authorization: Bearer <token>`
header or a `?token=` query param (used by `<audio>` tags and the WebSocket,
which can't set custom headers).
