(() => {
  const state = {
    liveSession: null,
    liveStartedAt: null,
    latestLive: null,
    paintScheduled: false,
    liveCtx: null,
    ws: null,
    clips: [],
    playingId: null,
    player: new Audio(),
  };

  const els = {
    healthDot: document.getElementById("health-dot"),
    healthLabel: document.getElementById("health-label"),
    listenToggle: document.getElementById("listen-toggle"),
    listenLabel: document.getElementById("listen-toggle-label"),
    liveLabel: document.getElementById("live-label"),
    voiceDot: document.getElementById("voice-dot"),
    voiceLabel: document.getElementById("voice-label"),
    liveCanvas: document.getElementById("live-canvas"),
    liveEmpty: document.getElementById("live-empty"),
    liveBadge: document.getElementById("live-badge"),
    liveMeta: document.getElementById("live-meta"),
    voiceList: document.getElementById("voice-list"),
    voiceEmpty: document.getElementById("voice-empty"),
    voiceCount: document.getElementById("voice-count"),
    voiceLive: document.getElementById("voice-live"),
    voiceAutoplay: document.getElementById("voice-autoplay"),
  };

  function apiBase() {
    const params = new URLSearchParams(location.search);
    const fromQuery = params.get("api");
    if (fromQuery) return fromQuery.replace(/\/$/, "");
    const configured = (window.HARMONY_CONFIG && window.HARMONY_CONFIG.apiBase) || "";
    if (configured) return configured.replace(/\/$/, "");
    if (location.port === "8000") return "";
    if (location.hostname !== "127.0.0.1" && location.hostname !== "localhost") {
      return `${location.protocol}//${location.hostname}:8000`;
    }
    return "http://127.0.0.1:8000";
  }

  function wsUrl(path) {
    const http = apiBase() || location.origin;
    const url = new URL(http, location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = path;
    url.search = "";
    url.hash = "";
    return url.toString();
  }

  function mediaUrl(path) {
    return `${apiBase()}${path}`;
  }

  function formatDuration(sec) {
    const total = Math.max(0, Math.round(sec || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function clipLength(ms) {
    const total = Math.max(0, Math.round((ms || 0) / 1000));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function clipWhen(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function elapsed(fromIso) {
    if (!fromIso) return "0:00";
    return formatDuration((Date.now() - new Date(fromIso).getTime()) / 1000);
  }

  function showLiveFrame(buffer) {
    state.latestLive = buffer;
    if (state.paintScheduled) return;
    state.paintScheduled = true;
    requestAnimationFrame(paintLive);
  }

  function paintLive() {
    const buffer = state.latestLive;
    state.latestLive = null;
    if (!buffer) {
      state.paintScheduled = false;
      return;
    }

    const blob = new Blob([buffer], { type: "image/jpeg" });
    const finish = () => {
      if (state.latestLive) requestAnimationFrame(paintLive);
      else state.paintScheduled = false;
    };

    const draw = (bitmap) => {
      const canvas = els.liveCanvas;
      const stage = canvas.parentElement;
      const sw = Math.max(1, stage.clientWidth);
      const sh = Math.max(1, stage.clientHeight);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const cw = Math.round(sw * dpr);
      const ch = Math.round(sh * dpr);
      if (canvas.width !== cw || canvas.height !== ch) {
        canvas.width = cw;
        canvas.height = ch;
        state.liveCtx = canvas.getContext("2d", { alpha: false, desynchronized: true });
      }
      if (!state.liveCtx) {
        state.liveCtx = canvas.getContext("2d", { alpha: false, desynchronized: true });
      }
      const ctx = state.liveCtx;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, sw, sh);
      const scale = Math.min(sw / bitmap.width, sh / bitmap.height);
      const w = bitmap.width * scale;
      const h = bitmap.height * scale;
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(bitmap, (sw - w) / 2, (sh - h) / 2, w, h);
      if (bitmap.close) bitmap.close();
      canvas.hidden = false;
      els.liveEmpty.hidden = true;
      els.liveBadge.hidden = false;
      if (!state.liveSession) {
        els.liveDot.className = "dot live";
        els.liveLabel.textContent = "Live";
      }
      finish();
    };

    if (typeof createImageBitmap === "function") {
      createImageBitmap(blob).then(draw).catch(finish);
    } else {
      finish();
    }
  }

  function setIdle() {
    state.liveSession = null;
    state.liveStartedAt = null;
    state.latestLive = null;
    els.liveCanvas.hidden = true;
    els.liveEmpty.hidden = false;
    els.liveBadge.hidden = true;
    els.liveDot.className = "dot";
    els.liveLabel.textContent = "Idle";
    els.liveMeta.textContent = "No active session";
  }

  function setSession(session) {
    state.liveSession = session;
    state.liveStartedAt = session.started_at;
    els.liveDot.className = "dot live";
    els.liveLabel.textContent = `Live · ${session.hostname || "PC"}`;
    renderLiveMeta();
  }

  function renderLiveMeta() {
    const session = state.liveSession;
    if (!session) {
      els.liveMeta.textContent = "No active session";
      return;
    }
    els.liveMeta.textContent = [
      session.hostname || "PC",
      session.username || "user",
      session.width && session.height ? `${session.width}×${session.height}` : null,
      session.fps ? `${session.fps} fps` : null,
      elapsed(state.liveStartedAt),
    ].filter(Boolean).join("  ·  ");
  }

  function upsertClip(clip, { play = false } = {}) {
    if (!clip || !clip.id) return;
    const existing = state.clips.findIndex((item) => item.id === clip.id);
    if (existing >= 0) state.clips.splice(existing, 1);
    state.clips.unshift(clip);
    state.clips = state.clips.slice(0, 80);
    renderClips();
    if (play && els.voiceAutoplay.checked) playClip(clip.id);
  }

  function renderClips() {
    const count = state.clips.length;
    els.voiceEmpty.hidden = count > 0;
    els.voiceCount.textContent = count
      ? `${count} saved on the backend`
      : "Saved when something is said into the mic";
    if (count) {
      els.voiceDot.className = "dot ok";
      els.voiceLabel.textContent = `Voice · ${count}`;
    } else {
      els.voiceDot.className = "dot";
      els.voiceLabel.textContent = "No voice yet";
    }

    els.voiceList.replaceChildren();
    for (const clip of state.clips) {
      const item = document.createElement("li");
      item.className = "voice-item" + (state.playingId === clip.id ? " playing" : "");
      item.dataset.id = clip.id;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "voice-play";
      button.setAttribute("aria-pressed", state.playingId === clip.id ? "true" : "false");
      button.setAttribute("aria-label", state.playingId === clip.id ? `Pause ${clip.transcript || "voice clip"}` : `Play ${clip.transcript || "voice clip"}`);
      button.textContent = state.playingId === clip.id ? "❚❚" : "▶";
      button.addEventListener("click", () => toggleClip(clip.id));

      const copy = document.createElement("div");
      copy.className = "voice-copy";
      const text = document.createElement("p");
      text.className = "voice-text";
      text.textContent = clip.transcript || "Speech captured (no transcript)";
      const meta = document.createElement("p");
      meta.className = "voice-meta";
      meta.innerHTML = "";
      if (clip.wake) {
        const badge = document.createElement("span");
        badge.className = "voice-badge";
        badge.textContent = "WAKE";
        meta.append(badge);
      }
      meta.append(
        document.createTextNode(
          [clipLength(clip.duration_ms), clipWhen(clip.created_at)].filter(Boolean).join("  ·  "),
        ),
      );
      copy.append(text, meta);
      item.append(button, copy);
      els.voiceList.append(item);
    }
  }

  function toggleClip(id) {
    if (state.playingId === id && !state.player.paused) {
      state.player.pause();
      state.playingId = null;
      renderClips();
      return;
    }
    playClip(id);
  }

  function playClip(id) {
    const clip = state.clips.find((item) => item.id === id);
    if (!clip) return;
    state.playingId = id;
    state.player.src = mediaUrl(clip.url || `/api/audio/${id}`);
    const play = state.player.play();
    if (play && typeof play.catch === "function") {
      play.catch(() => {
        state.clips = state.clips.filter((item) => item.id !== id);
        state.playingId = null;
        renderClips();
      });
    }
    renderClips();
  }

  function onVoice(clip) {
    const text = clip.transcript || "Speech captured";
    els.voiceLive.textContent = `New voice clip: ${text}`;
    upsertClip(clip, { play: true });
  }

  async function loadClips() {
    try {
      const response = await fetch(`${apiBase()}/api/audio?limit=40`);
      if (!response.ok) return;
      const data = await response.json();
      const items = Array.isArray(data.items) ? data.items : [];
      state.clips = items;
      renderClips();
    } catch (_err) {
      // Backend may still be starting.
    }
  }

  state.player.addEventListener("ended", () => {
    state.playingId = null;
    renderClips();
  });
  state.player.addEventListener("pause", () => {
    if (state.player.ended) return;
    if (state.player.currentTime > 0 && state.player.currentTime < state.player.duration) {
      renderClips();
    }
  });

  function setListenState(payload) {
    const enabled = Boolean(payload && payload.enabled);
    const connected = Boolean(payload && payload.assistant_connected);
    els.listenToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    if (enabled && connected) {
      els.listenLabel.textContent = "Listening for commands";
    } else if (enabled) {
      els.listenLabel.textContent = "On — waiting for desktop app";
    } else {
      els.listenLabel.textContent = "Voice assistant off";
    }
    els.listenToggle.title = connected
      ? (enabled ? "Stop listening" : "Start listening for voice commands")
      : "Start the desktop app, then turn this on to use the microphone";
  }

  async function toggleListen() {
    const enabled = els.listenToggle.getAttribute("aria-pressed") === "true";
    els.listenToggle.disabled = true;
    try {
      const response = await fetch(`${apiBase()}/api/listen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !enabled }),
      });
      if (!response.ok) return;
      setListenState(await response.json());
    } catch (_err) {
      // Backend may be down.
    } finally {
      els.listenToggle.disabled = false;
    }
  }

  async function loadListen() {
    try {
      const response = await fetch(`${apiBase()}/api/listen`);
      if (!response.ok) return;
      setListenState(await response.json());
    } catch (_err) {
      // Backend may still be starting.
    }
  }

  function connectLive() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const socket = new WebSocket(wsUrl("/ws/live"));
    socket.binaryType = "arraybuffer";
    state.ws = socket;

    socket.addEventListener("open", () => {
      els.healthDot.className = "dot ok";
      els.healthLabel.textContent = "Backend online";
      loadClips();
      loadListen();
    });

    socket.addEventListener("message", (event) => {
      if (typeof event.data === "string") {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "session") setSession(payload);
          if (payload.type === "idle") setIdle();
          if (payload.type === "voice") onVoice(payload);
          if (payload.type === "listen") setListenState(payload);
        } catch (_err) {
          // Ignore malformed control messages.
        }
        return;
      }
      showLiveFrame(event.data);
    });

    socket.addEventListener("close", () => {
      if (state.ws === socket) state.ws = null;
      els.healthDot.className = "dot err";
      els.healthLabel.textContent = "Reconnecting…";
      setTimeout(connectLive, 800);
    });

    socket.addEventListener("error", () => {
      socket.close();
    });
  }

  els.listenToggle.addEventListener("click", toggleListen);
  connectLive();
  loadClips();
  loadListen();
  setInterval(renderLiveMeta, 1000);
})();
