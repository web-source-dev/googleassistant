(() => {
  const state = {
    liveSession: null,
    liveStartedAt: null,
    latestLive: null,
    paintScheduled: false,
    liveCtx: null,
    ws: null,
    clips: [],
    joins: [],
    playingId: null,
    player: new Audio(),
    paused: false,
    hasFrame: false,
    viewerCount: 0,
    pipActive: false,
    pipStream: null,
    pipWindow: null,
  };

  const els = {
    healthDot: document.getElementById("health-dot"),
    healthLabel: document.getElementById("health-label"),
    listenToggle: document.getElementById("listen-toggle"),
    listenLabel: document.getElementById("listen-toggle-label"),
    liveLabel: document.getElementById("live-label"),
    liveDot: document.getElementById("live-dot"),
    voiceDot: document.getElementById("voice-dot"),
    voiceLabel: document.getElementById("voice-label"),
    liveStage: document.getElementById("live-stage"),
    liveCanvas: document.getElementById("live-canvas"),
    liveEmpty: document.getElementById("live-empty"),
    liveBadge: document.getElementById("live-badge"),
    liveBadgeText: document.getElementById("live-badge-text"),
    liveMeta: document.getElementById("live-meta"),
    livePause: document.getElementById("live-pause"),
    livePip: document.getElementById("live-pip"),
    livePipVideo: document.getElementById("live-pip-video"),
    liveSnap: document.getElementById("live-snap"),
    liveFull: document.getElementById("live-full"),
    joinList: document.getElementById("join-list"),
    joinEmpty: document.getElementById("join-empty"),
    joinCount: document.getElementById("join-count"),
    voiceList: document.getElementById("voice-list"),
    voiceEmpty: document.getElementById("voice-empty"),
    voiceCount: document.getElementById("voice-count"),
    voiceLive: document.getElementById("voice-live"),
    voiceAutoplay: document.getElementById("voice-autoplay"),
    sidebarToggle: document.getElementById("sidebar-toggle"),
    sidePanel: document.getElementById("side-panel"),
    main: document.getElementById("main"),
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
    state.hasFrame = true;
    if (state.paused) {
      updateLiveControls();
      return;
    }
    if (state.paintScheduled) return;
    state.paintScheduled = true;
    schedulePaint();
  }

  function schedulePaint() {
    if (state.pipActive || document.hidden) {
      setTimeout(paintLive, 50);
      return;
    }
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
      if (state.paused) {
        state.paintScheduled = false;
        return;
      }
      if (state.latestLive) schedulePaint();
      else state.paintScheduled = false;
    };

    const draw = (bitmap) => {
      const canvas = els.liveCanvas;
      const stage = canvas.parentElement;
      const sw = Math.max(1, stage.clientWidth);
      const sh = Math.max(1, stage.clientHeight);
      const dpr = Math.min(window.devicePixelRatio || 1, 1.25);
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
      const sharp = scale >= 0.98 && scale <= 1.02;
      ctx.imageSmoothingEnabled = !sharp;
      if (!sharp) ctx.imageSmoothingQuality = "medium";
      ctx.drawImage(bitmap, (sw - w) / 2, (sh - h) / 2, w, h);
      copyPipFrame(bitmap);
      if (bitmap.close) bitmap.close();
      canvas.hidden = false;
      els.liveEmpty.hidden = true;
      updateLiveBadge();
      updateLiveControls();
      if (!state.liveSession && els.liveDot) {
        els.liveDot.className = "dot live";
        els.liveLabel.textContent = "Live";
      }
      finish();
    };

    if (typeof createImageBitmap === "function") {
      createImageBitmap(blob, { colorSpaceConversion: "none" }).then(draw).catch(() => decodeWithImage(blob, draw, finish));
    } else {
      decodeWithImage(blob, draw, finish);
    }
  }

  function decodeWithImage(blob, draw, finish) {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      draw(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      finish();
    };
    img.src = url;
  }

  function setIdle() {
    state.liveSession = null;
    state.liveStartedAt = null;
    state.latestLive = null;
    state.hasFrame = false;
    state.paused = false;
    void closeMiniPlayer();
    els.liveCanvas.hidden = true;
    els.liveEmpty.hidden = false;
    updateLiveBadge();
    updateLiveControls();
    if (els.liveDot) els.liveDot.className = "dot";
    els.liveLabel.textContent = "Idle";
    renderLiveMeta();
  }

  function setSession(session) {
    state.liveSession = session;
    state.liveStartedAt = session.started_at;
    if (els.liveDot) els.liveDot.className = "dot live";
    els.liveLabel.textContent = `Live · ${session.hostname || "PC"}`;
    updateLiveBadge();
    renderLiveMeta();
  }

  function setViewerCount(count) {
    state.viewerCount = Math.max(0, Number(count) || 0);
    updateLiveBadge();
    renderLiveMeta();
  }

  function updateLiveBadge() {
    const live = Boolean(state.liveSession || state.hasFrame);
    els.liveBadge.hidden = !live;
    if (!els.liveBadgeText) return;
    if (state.paused) {
      els.liveBadgeText.textContent = "PAUSED";
      return;
    }
    const watchers = state.viewerCount ? ` · ${state.viewerCount}` : "";
    els.liveBadgeText.textContent = `LIVE${watchers}`;
  }

  function updateLiveControls() {
    els.livePause.setAttribute("aria-pressed", state.paused ? "true" : "false");
    els.livePause.textContent = state.paused ? "Resume" : "Pause";
    els.livePause.disabled = !state.hasFrame && !state.liveSession;
    els.liveSnap.disabled = !state.hasFrame;
    els.livePip.disabled = !state.hasFrame;
    els.livePip.setAttribute("aria-pressed", state.pipActive ? "true" : "false");
    els.livePip.textContent = state.pipActive ? "Close mini" : "Mini player";
  }

  function renderLiveMeta() {
    const session = state.liveSession;
    if (!session) {
      els.liveMeta.textContent = state.viewerCount
        ? `No active session · ${state.viewerCount} watching`
        : "No active session";
      return;
    }
    els.liveMeta.textContent = [
      session.hostname || "PC",
      session.username || "user",
      session.width && session.height ? `${session.width}×${session.height}` : null,
      session.fps ? `${session.fps} fps` : null,
      elapsed(state.liveStartedAt),
      state.viewerCount ? `${state.viewerCount} watching` : null,
      state.paused ? "paused" : null,
      state.pipActive ? "mini player" : null,
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

  function applySidebar(hidden) {
    els.main.classList.toggle("sidebar-hidden", hidden);
    els.sidePanel.hidden = hidden;
    els.sidebarToggle.setAttribute("aria-pressed", hidden ? "false" : "true");
    els.sidebarToggle.textContent = hidden ? "Show sidebar" : "Hide sidebar";
    els.sidebarToggle.title = hidden ? "Show the share times and voice panel" : "Hide the share times and voice panel";
  }

  function toggleSidebar() {
    const hidden = !els.main.classList.contains("sidebar-hidden");
    applySidebar(hidden);
    try {
      localStorage.setItem("piano-sidebar-hidden", hidden ? "1" : "0");
    } catch (_err) {
      // Private mode may block storage.
    }
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

  function joinWhen(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const day = date.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
    const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return `${day} ${time}`;
  }

  function upsertJoin(entry) {
    if (!entry || !entry.at || entry.event !== "session") return;
    if (state.joins.some((item) => item.at === entry.at && item.event === "session")) return;
    state.joins.unshift({ at: entry.at, event: "session" });
    state.joins = state.joins.slice(0, 80);
    renderJoins();
  }

  function setJoins(items) {
    state.joins = (Array.isArray(items) ? items : [])
      .filter((item) => item && item.at && item.event === "session")
      .map((item) => ({ at: item.at, event: "session" }))
      .slice(0, 80);
    renderJoins();
  }

  function renderJoins() {
    const count = state.joins.length;
    els.joinEmpty.hidden = count > 0;
    els.joinCount.textContent = count
      ? `${count} share ${count === 1 ? "time" : "times"}`
      : "Date and time the PC started sharing the screen";
    els.joinList.replaceChildren();
    for (const entry of state.joins) {
      const item = document.createElement("li");
      item.className = "join-item";
      const time = document.createElement("time");
      time.dateTime = entry.at;
      time.textContent = joinWhen(entry.at);
      const kind = document.createElement("span");
      kind.textContent = "Screen share";
      item.append(time, kind);
      els.joinList.append(item);
    }
  }

  async function loadJoins() {
    try {
      const response = await fetch(`${apiBase()}/api/joins?limit=80`);
      if (!response.ok) return;
      const data = await response.json();
      setJoins(data.items);
    } catch (_err) {
      // Backend may still be starting.
    }
  }

  function copyPipFrame(bitmap) {
    const ctx = state.pipCtx;
    if (!ctx || !state.pipWindow) return;
    const canvas = ctx.canvas;
    const sw = canvas.width;
    const sh = canvas.height;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, sw, sh);
    const scale = Math.min(sw / bitmap.width, sh / bitmap.height);
    const w = bitmap.width * scale;
    const h = bitmap.height * scale;
    ctx.drawImage(bitmap, (sw - w) / 2, (sh - h) / 2, w, h);
  }

  function isVideoPipOpen() {
    return Boolean(document.pictureInPictureElement);
  }

  async function toggleMiniPlayer() {
    if (state.pipActive || isVideoPipOpen()) {
      await closeMiniPlayer();
      return;
    }
    if (!state.hasFrame || els.liveCanvas.hidden) return;
    try {
      await openVideoPip();
    } catch (_videoErr) {
      try {
        await openDocumentPip();
      } catch (_docErr) {
        els.livePip.title = "Mini player needs Chrome, Edge, or Safari";
      }
    }
    updateLiveControls();
    renderLiveMeta();
  }

  async function openVideoPip() {
    if (!document.pictureInPictureEnabled || !els.livePipVideo.requestPictureInPicture) {
      throw new Error("video-pip-unavailable");
    }
    if (!state.pipStream) {
      state.pipStream = els.liveCanvas.captureStream(15);
      els.livePipVideo.srcObject = state.pipStream;
    }
    els.livePipVideo.muted = true;
    await els.livePipVideo.play();
    await els.livePipVideo.requestPictureInPicture();
    state.pipActive = true;
  }

  async function openDocumentPip() {
    if (!window.documentPictureInPicture || !window.documentPictureInPicture.requestWindow) {
      throw new Error("document-pip-unavailable");
    }
    const pipWindow = await window.documentPictureInPicture.requestWindow({
      width: 480,
      height: 270,
    });
    const doc = pipWindow.document;
    doc.head.appendChild(doc.createElement("style")).textContent =
      "html,body{margin:0;height:100%;background:#000;overflow:hidden}canvas{width:100%;height:100%;display:block}";
    const canvas = doc.createElement("canvas");
    canvas.width = 960;
    canvas.height = 540;
    doc.body.appendChild(canvas);
    state.pipWindow = pipWindow;
    state.pipCtx = canvas.getContext("2d", { alpha: false });
    state.pipActive = true;
    pipWindow.addEventListener("pagehide", () => {
      if (state.pipWindow === pipWindow) {
        state.pipWindow = null;
        state.pipCtx = null;
        state.pipActive = isVideoPipOpen();
        updateLiveControls();
        renderLiveMeta();
      }
    });
  }

  async function closeMiniPlayer() {
    try {
      if (isVideoPipOpen()) await document.exitPictureInPicture();
    } catch (_err) {
      // Already closed.
    }
    if (state.pipWindow) {
      try {
        state.pipWindow.close();
      } catch (_err) {
        // Already closed.
      }
    }
    state.pipWindow = null;
    state.pipCtx = null;
    state.pipActive = false;
    updateLiveControls();
    renderLiveMeta();
  }

  function togglePause() {
    if (!state.hasFrame && !state.liveSession) return;
    state.paused = !state.paused;
    updateLiveBadge();
    updateLiveControls();
    renderLiveMeta();
    if (!state.paused && state.latestLive && !state.paintScheduled) {
      state.paintScheduled = true;
      schedulePaint();
    }
  }

  function saveSnapshot() {
    if (!state.hasFrame || els.liveCanvas.hidden) return;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    els.liveCanvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `piano-live-${stamp}.jpg`;
      link.click();
      URL.revokeObjectURL(url);
    }, "image/jpeg", 0.92);
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }
      await els.liveStage.requestFullscreen();
    } catch (_err) {
      // Fullscreen can be blocked by the browser.
    }
  }

  function onLiveKey(event) {
    if (event.target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(event.target.tagName) && event.key !== " ") {
      return;
    }
    if (event.target && event.target.tagName === "BUTTON" && event.key === " ") return;
    const key = event.key.toLowerCase();
    if (key === " " || key === "k") {
      event.preventDefault();
      togglePause();
    } else if (key === "p") {
      event.preventDefault();
      toggleMiniPlayer();
    } else if (key === "f") {
      event.preventDefault();
      toggleFullscreen();
    } else if (key === "s" && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      saveSnapshot();
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
      loadJoins();
    });

    socket.addEventListener("message", (event) => {
      if (typeof event.data === "string") {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "session") setSession(payload);
          if (payload.type === "idle") setIdle();
          if (payload.type === "voice") onVoice(payload);
          if (payload.type === "listen") setListenState(payload);
          if (payload.type === "viewers") setViewerCount(payload.count);
          if (payload.type === "joins") setJoins(payload.items);
          if (payload.type === "join") upsertJoin(payload);
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
  els.sidebarToggle.addEventListener("click", toggleSidebar);
  els.livePause.addEventListener("click", togglePause);
  els.livePip.addEventListener("click", toggleMiniPlayer);
  els.liveSnap.addEventListener("click", saveSnapshot);
  els.liveFull.addEventListener("click", toggleFullscreen);
  els.liveStage.addEventListener("dblclick", (event) => {
    if (event.target.closest(".live-toolbar")) return;
    toggleFullscreen();
  });
  document.addEventListener("keydown", onLiveKey);
  els.livePipVideo.addEventListener("enterpictureinpicture", () => {
    state.pipActive = true;
    updateLiveControls();
    renderLiveMeta();
  });
  els.livePipVideo.addEventListener("leavepictureinpicture", () => {
    if (!state.pipWindow) state.pipActive = false;
    updateLiveControls();
    renderLiveMeta();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) return;
    if (state.pipActive && state.latestLive && !state.paintScheduled) {
      state.paintScheduled = true;
      schedulePaint();
    }
  });
  connectLive();
  loadClips();
  loadListen();
  loadJoins();
  updateLiveControls();
  renderJoins();
  applySidebar(localStorage.getItem("piano-sidebar-hidden") === "1");
  setInterval(renderLiveMeta, 1000);
})();
