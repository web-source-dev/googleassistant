# Google Assistant

Windows tray assistant. Say the Turkish wake word, then what to open. While it runs, it can stream the desktop live to [http://127.0.0.1:8000](http://127.0.0.1:8000). Spoken audio is sent to the backend and saved there.

## Wake phrase

**`asistan`** (change it in Settings)

Same sentence:

- *asistan YouTube aç*
- *asistan Discord*
- *asistan e-Devlet*
- *asistan e-okul*

Or: *asistan* → wait for the beep/status → *YouTube aç*

Also accepted: *hey asistan*, *assistant* (if speech-to-text hears it that way).

## Install (Windows)

Do not run the raw build folder. Use the setup wizard:

```bash
cd voice-assistant
python build_installer.py
```

Then run `release/GoogleAssistant.exe`. It installs into `C:\Program Files\Google Assistant`. Config goes to `%LOCALAPPDATA%\Google Assistant`, not next to the installer.

Building the installer also copies it to `backend/data/updates/` so installed PCs can silent-update from the live backend. Bump `src/version.py`, rebuild, keep the backend running; the tray app downloads the new installer and installs it without a wizard, then shows a notification whether it updated or was already current.

## Setup

Start the recording backend first, then this app:

```bash
cd ../backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
cd ../voice-assistant
pip install -r requirements.txt
python main.py
```

Or `run.bat` in each folder.

Dashboard: [http://127.0.0.1:8000](http://127.0.0.1:8000) — live desktop stream.

## Live stream

Streaming starts with the app. Frames go to the backend and show immediately on the web page. Screen frames are not written to disk.

When the microphone captures speech, that clip is sent to the backend as WAV audio (with the transcript when speech-to-text succeeds). Open [http://127.0.0.1:8000](http://127.0.0.1:8000) to play saved clips.

If the backend is down, the assistant keeps capturing the newest frame and queues voice clips until it reconnects.

Settings: backend URL, FPS, JPEG quality, max width, send spoken audio.

## Tips if it does not hear you

- Speak clearly: **asistan** then the app/site name
- Stay close to the microphone
- Pause from the tray in noisy rooms
- Lower **Energy Threshold** in Settings if it never triggers (try 100–150)
- Raise it if background noise triggers it (try 200–250)

## Examples

| Say | Opens |
|-----|--------|
| *asistan YouTube aç* | YouTube |
| *asistan Discord* | Discord |
| *asistan e-Devlet* | turkiye.gov.tr |
| *asistan EBA* / *e-okul* / *MEB* | Education portals |
| *asistan Trendyol* | trendyol.com |
| *asistan python ara* | Google search |

## License

MIT
