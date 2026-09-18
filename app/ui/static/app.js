// Google Flow Auto Frontend Logic

let ws = null;
let currentStatus = null;

// DOM Elements
const appStateBadge = document.getElementById("app-state-badge");
const alertBanner = document.getElementById("alert-banner");
const alertMessage = document.getElementById("alert-message");
const alertDismiss = document.getElementById("alert-dismiss");

const progressBarFill = document.getElementById("overall-progress-bar");
const progressCounts = document.getElementById("progress-counts");
const statTotal = document.getElementById("stat-total");
const statCompleted = document.getElementById("stat-completed");
const statRemaining = document.getElementById("stat-remaining");
const statFailed = document.getElementById("stat-failed");

const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnResume = document.getElementById("btn-resume");
const btnStop = document.getElementById("btn-stop");

const currentStatusTag = document.getElementById("current-status-tag");
const currentVideo = document.getElementById("current-video");
const currentScene = document.getElementById("current-scene");
const currentRetries = document.getElementById("current-retries");
const currentPromptText = document.getElementById("current-prompt-text");

const videoGroupsList = document.getElementById("video-groups-list");
const logConsole = document.getElementById("log-console");
const btnClearLogs = document.getElementById("btn-clear-logs");

const promptsModal = document.getElementById("prompts-modal");
const btnOpenPrompts = document.getElementById("btn-open-prompts");
const modalClose = document.getElementById("modal-close");
const promptsTextarea = document.getElementById("prompts-textarea");
const validationCounter = document.getElementById("validation-counter");
const validationHint = document.getElementById("validation-hint");
const btnLoadSample = document.getElementById("btn-load-sample");
const btnSavePrompts = document.getElementById("btn-save-prompts");

const videoModal = document.getElementById("video-modal");
const videoModalClose = document.getElementById("video-modal-close");
const videoModalTitle = document.getElementById("video-modal-title");
const previewPlayer = document.getElementById("preview-player");

// Init
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  connectWebSocket();
  fetchStatus();
});

function setupEventListeners() {
  btnStart.addEventListener("click", () => sendAction("/api/start"));
  btnPause.addEventListener("click", () => sendAction("/api/pause"));
  btnResume.addEventListener("click", () => sendAction("/api/resume"));
  btnStop.addEventListener("click", () => sendAction("/api/stop"));

  alertDismiss.addEventListener("click", () => {
    alertBanner.classList.add("hidden");
  });

  btnClearLogs.addEventListener("click", () => {
    logConsole.innerHTML = "";
  });

  // Prompts modal
  btnOpenPrompts.addEventListener("click", () => promptsModal.classList.remove("hidden"));
  modalClose.addEventListener("click", () => promptsModal.classList.add("hidden"));
  promptsTextarea.addEventListener("input", handlePromptsInput);
  btnLoadSample.addEventListener("click", loadSamplePrompts);
  btnSavePrompts.addEventListener("click", savePromptsToQueue);

  // Video preview modal
  videoModalClose.addEventListener("click", () => {
    previewPlayer.pause();
    previewPlayer.src = "";
    videoModal.classList.add("hidden");
  });
}

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    appendLog("[WebSocket] Connected to controller.");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "status") {
        renderStatus(msg.data);
      } else if (msg.type === "log") {
        appendLog(msg.data);
      }
    } catch (e) {
      console.error("Error parsing WS message", e);
    }
  };

  ws.onclose = () => {
    appendLog("[WebSocket] Disconnected. Reconnecting in 3s...");
    setTimeout(connectWebSocket, 3000);
  };
}

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      renderStatus(data);
    }
  } catch (e) {
    console.error("Failed to fetch initial status", e);
  }
}

async function sendAction(endpoint) {
  try {
    const res = await fetch(endpoint, { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      showAlert(err.detail || "Action failed");
    }
    fetchStatus();
  } catch (e) {
    showAlert(`Request error: ${e.message}`);
  }
}

function renderStatus(data) {
  currentStatus = data;
  const state = data.state || "IDLE";

  // App state badge
  appStateBadge.textContent = state;
  appStateBadge.className = `badge state-${state.toLowerCase()}`;

  // Error Banner
  if (data.last_error) {
    showAlert(data.last_error);
  } else if (state === "AUTH_REQUIRED") {
    showAlert("Google Flow authentication required! Please log in on the browser and click RESUME.");
  } else {
    alertBanner.classList.add("hidden");
  }

  // Summary Metrics
  const summary = data.summary || { total: 0, completed: 0, remaining: 0, failed: 0 };
  const total = summary.total || 0;
  const completed = summary.completed || 0;
  const remaining = summary.remaining || 0;
  const failed = summary.failed || 0;

  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  progressBarFill.style.width = `${pct}%`;
  progressCounts.textContent = `${completed} / ${total} scenes completed (${pct}%)`;

  statTotal.textContent = total;
  statCompleted.textContent = completed;
  statRemaining.textContent = remaining;
  statFailed.textContent = failed;

  // Current Scene
  const curr = data.current_scene;
  if (curr) {
    currentVideo.textContent = `Video ${String(curr.video_number).padStart(2, "0")}`;
    currentScene.textContent = `Scene ${String(curr.scene_number).padStart(2, "0")} / 06`;
    currentRetries.textContent = curr.retry_count || 0;
    currentPromptText.textContent = curr.prompt;

    currentStatusTag.textContent = curr.status;
    currentStatusTag.className = `tag tag-${curr.status.toLowerCase()}`;
  } else {
    currentVideo.textContent = "—";
    currentScene.textContent = "—";
    currentRetries.textContent = "0";
    currentPromptText.textContent = state === "RUNNING" ? "Preparing next scene..." : "No scene currently in progress.";
    currentStatusTag.textContent = state;
    currentStatusTag.className = "tag tag-waiting";
  }

  // Video Groups List
  renderVideoGroups(data.video_groups || []);
}

function renderVideoGroups(groups) {
  if (!groups || groups.length === 0) {
    videoGroupsList.innerHTML = `<p class="empty-hint">No queue loaded. Click 'Prompts Queue' to load 60 prompts.</p>`;
    return;
  }

  videoGroupsList.innerHTML = "";
  groups.forEach((g) => {
    const vNum = String(g.video_number).padStart(2, "0");
    const item = document.createElement("div");
    item.className = "video-item";
    item.id = `video-group-${g.video_number}`;

    let icon = "○";
    let statusText = "Waiting";
    if (g.is_complete && g.merged_file_path) {
      icon = "✓";
      statusText = "Completed";
    } else if (g.completed_count > 0) {
      icon = "⏳";
      statusText = `${g.completed_count}/6 scenes`;
    }

    let previewBtn = "";
    if (g.merged_file_path) {
      previewBtn = `<button class="btn-preview" onclick="playVideo('/api/videos/${g.video_number}', 'Video ${vNum} (Full 48s)')">▶ Play Video</button>`;
    }

    item.innerHTML = `
      <div class="video-item-header" onclick="toggleAccordion(${g.video_number})">
        <div class="video-title-area">
          <span class="video-status-icon">${icon}</span>
          <strong>Video ${vNum}</strong>
          <span class="subtext">${statusText}</span>
        </div>
        <div class="video-actions">
          ${previewBtn}
          <span class="subtext">▾</span>
        </div>
      </div>
      <div class="scenes-accordion">
        ${renderScenesRows(g.scenes, g.video_number)}
      </div>
    `;

    videoGroupsList.appendChild(item);
  });
}

function renderScenesRows(scenes, videoNumber) {
  if (!scenes || scenes.length === 0) return "<p>No scenes</p>";

  return scenes.map((s) => {
    const sNum = String(s.scene_number).padStart(2, "0");
    const sId = String(s.scene_id).padStart(2, "0");

    let actions = "";
    if (s.status === "COMPLETED" && s.file_path) {
      actions += `<button class="btn-sm btn-secondary" onclick="playVideo('/api/clips/${videoNumber}/${s.scene_number}', 'Scene ${sNum} (Clip)')">▶ Clip</button>`;
    } else if (s.status === "FAILED") {
      actions += `<button class="btn-sm btn-secondary" onclick="retryScene(${s.scene_id})">↺ Retry</button>`;
    }

    return `
      <div class="scene-row">
        <div class="scene-info" title="${s.prompt}">
          <span class="tag tag-${s.status.toLowerCase()}">${s.status}</span>
          <span>#${sId} Scene ${sNum}: ${s.prompt}</span>
        </div>
        <div class="scene-actions">
          ${actions}
        </div>
      </div>
    `;
  }).join("");
}

function toggleAccordion(videoNumber) {
  const item = document.getElementById(`video-group-${videoNumber}`);
  if (item) {
    item.classList.toggle("open");
  }
}

function playVideo(url, title) {
  videoModalTitle.textContent = title;
  previewPlayer.src = url;
  videoModal.classList.remove("hidden");
  previewPlayer.play().catch(() => {});
}

async function retryScene(sceneId) {
  try {
    await fetch(`/api/retry/${sceneId}`, { method: "POST" });
    fetchStatus();
  } catch (e) {
    showAlert(`Retry error: ${e.message}`);
  }
}

function showAlert(msg) {
  alertMessage.textContent = msg;
  alertBanner.classList.remove("hidden");
}

function appendLog(line) {
  const div = document.createElement("div");
  div.className = "log-line";
  div.textContent = line;
  logConsole.appendChild(div);
  logConsole.scrollTop = logConsole.scrollHeight;
}

// Prompts Input Validation
function handlePromptsInput() {
  const text = promptsTextarea.value.trim();
  if (!text) {
    validationCounter.textContent = "Prompts: 0";
    validationHint.textContent = "60 prompts required for 10 complete videos.";
    validationCounter.style.color = "var(--text-muted)";
    return;
  }

  // Count prompts by blank lines
  const lines = text.split(/\n\s*\n+/).map(l => l.trim()).filter(l => l && !l.startsWith("#"));
  const count = lines.length;
  validationCounter.textContent = `Prompts: ${count}`;

  const remainder = count % 6;
  if (remainder !== 0) {
    const missing = 6 - remainder;
    validationHint.textContent = `Currently loaded: ${count}. Missing ${missing} to complete Video ${Math.floor(count / 6) + 1}.`;
    validationCounter.style.color = "var(--warning)";
  } else {
    validationHint.textContent = `${count} prompts loaded (${count / 6} complete videos of 6 scenes each).`;
    validationCounter.style.color = "var(--success)";
  }
}

function loadSamplePrompts() {
  let sample = "";
  for (let v = 1; v <= 10; v++) {
    const vStr = String(v).padStart(2, "0");
    sample += `VIDEO ${vStr}\n`;
    for (let s = 1; s <= 6; s++) {
      const sOverall = (v - 1) * 6 + s;
      sample += `A cinematic 8-second sequence of Video ${vStr} Scene ${s} showing visual progression #${sOverall}.\n`;
    }
    sample += "\n";
  }
  promptsTextarea.value = sample.trim();
  handlePromptsInput();
}

async function savePromptsToQueue() {
  const text = promptsTextarea.value.trim();
  if (!text) {
    alert("Please enter prompts.");
    return;
  }

  try {
    const res = await fetch("/api/prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompts_text: text, overwrite: true })
    });

    const data = await res.json();
    if (res.ok) {
      promptsModal.classList.add("hidden");
      showAlert(`Successfully loaded ${data.total_prompts} prompts into queue!`);
      fetchStatus();
    } else {
      alert(`Validation error:\n${data.detail}`);
    }
  } catch (e) {
    alert(`Failed to save prompts: ${e.message}`);
  }
}
