# Google Assistant Backend

Relays the voice-assistant desktop stream to the browser. Frames are not saved.
Spoken microphone clips are saved as WAV files and can be played on the live page.

## Setup

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Or `run.bat`.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Backend status |
| GET | `/api/live` | Current live session |
| GET | `/api/live/frame` | Latest JPEG |
| GET | `/api/audio` | List saved voice clips |
| GET | `/api/audio/{id}` | Download / play a WAV clip |
| POST | `/api/audio` | Upload a spoken clip from the desktop app |
| WS | `/ws/record` | Frames in from the desktop app |
| WS | `/ws/live` | Frames and new-clip events out to the web viewer |
