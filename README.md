# Google Flow Auto ⚡

A local, resilient automation utility for bulk video generation on [Google Flow](https://flow.google.com) and automated scene assembly with FFmpeg.

---

## 📖 What It Does

Google Flow Auto automates the full pipeline from raw text prompts to finished, multi-scene merged videos:

```text
60 Prompts Queue
      │
      ├── Video 01
      │    ├── Scene 01 (~8s) ─► Download
      │    ├── Scene 02 (~8s) ─► Download
      │    ├── Scene 03 (~8s) ─► Download
      │    ├── Scene 04 (~8s) ─► Download
      │    ├── Scene 05 (~8s) ─► Download
      │    └── Scene 06 (~8s) ─► Download
      │             │
      │       FFmpeg Merge
      │             ▼
      │       Video_01.mp4 (~48s)
      │
      ├── Video 02 (Scenes 07–12) ─► Video_02.mp4
      │    ...
      └── Video 10 (Scenes 55–60) ─► Video_10.mp4
```

### Final Output
- **10 × ~48-second merged MP4 videos** (`Video_01.mp4` through `Video_10.mp4`)
- **60 × individual source scene clips** (`scene_01.mp4` through `scene_06.mp4` per video directory)

---

## 🚀 Key Features

- **Isolated Flow Automation:** All browser selectors and interaction rules are strictly isolated in `app/flow/selectors.py`.
- **Intelligent Polling:** No fixed-time sleeps. Monitors actual DOM state, generation spinners, and media readiness with configurable timeout safeguards.
- **SQLite Checkpoint & Crash Recovery:** Atomic transaction logging prevents re-generating already completed scenes. If interrupted or crashed, restarts from the first incomplete scene.
- **FFmpeg Stream Copy & Re-encode Fallback:** Probes media streams with `ffprobe`. Uses ultra-fast stream copy concatenation when compatible, falling back to clean H.264/AAC re-encoding if streams differ.
- **Responsive Web UI:** Modern, touch-friendly dark UI optimized for mobile phones (320px–412px) and desktop screens (1366px+).
- **Full CLI:** Complete headless terminal controls (`start`, `status`, `pause`, `resume`, `retry`, `serve`).
- **Test Mode / Mock Engine:** Built-in synthetic clip generator (`--mock`) for testing full pipelines on headless environments like Android/UserLAnd, Linux terminals, or CI/CD pipelines without launching Chrome.
- **Zero Credential Theft:** Does **not** store Google passwords or bypass CAPTCHAs. Uses persistent browser profiles where the user logs in manually once.

---

## 📋 System Requirements

- **Operating System:** Windows 10/11 (recommended for desktop Chrome automation), Linux (Debian/Ubuntu/Arch), macOS, or Android (via UserLAnd Debian for CLI/monitoring).
- **Python:** 3.10, 3.11, 3.12, or 3.13.
- **FFmpeg & FFprobe:** Installed and available on system `$PATH`.
- **Browser:** Google Chrome or Chromium (managed via Playwright).
- **Google Account:** Valid account with access to [Google Flow](https://flow.google.com).

---

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone git@github.com:Aryan1027/Google_Flow_Auto.git
   cd Google_Flow_Auto
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Ensure FFmpeg is installed:**
   ```bash
   # Debian / Ubuntu / UserLAnd:
   sudo apt-get install ffmpeg

   # Windows (via Chocolatey or Scoop):
   choco install ffmpeg
   # or scoop install ffmpeg
   ```

---

## 📝 Prompt Preparation

Prompts can be supplied in two supported formats:

### Format A: Grouped with Headers (Recommended)
```text
VIDEO 01
Establishing shot of futuristic neon city at dusk.
Tracking shot of electric autonomous vehicle.
Operator serving steaming ramen under holograms.
Close-up of holographic glasses glowing cyan.
Aerial shot descending between skyscrapers.
Slow-motion rain droplets against neon signage.

VIDEO 02
Wide shot of mist clearing over mountain sunrise.
...
```

### Format B: Blank-Line Separated
```text
Establishing shot of futuristic neon city at dusk.

Tracking shot of electric autonomous vehicle.

Operator serving steaming ramen under holograms.
...
```

> **Validation Rule:** Total prompts must be divisible by 6 (e.g., 60 prompts for 10 videos). The validator alerts you immediately if any are missing:
> ```text
> 60 prompts required for 10 complete videos.
> Currently loaded: 58
> Missing: 2
> ```

A sample file with 60 valid prompts is provided at `data/prompts_sample.txt`.

---

## 💻 Running the Application

### 1. Launch the Responsive Web UI
```bash
python -m app serve
```
Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)** in your browser.

- Touch-friendly `[START]`, `[PAUSE]`, `[RESUME]`, and `[STOP]` controls.
- Real-time WebSocket event logs and progress bar.
- Direct video preview modal to watch completed clips or merged videos.
- Prompt editor with instant count validation.

#### Optional: LAN Access for Phone Monitoring
To control or monitor the automation running on your laptop from your phone:
```bash
python -m app serve --lan
```
> ⚠️ **Security Notice:** Binding to LAN (`0.0.0.0`) exposes the control interface to devices on your local Wi-Fi. Only use on trusted private networks.

---

### 2. Command-Line Interface (CLI)

- **Check Current Status:**
  ```bash
  python -m app status
  ```

- **Load Prompts into Queue:**
  ```bash
  python -m app load-prompts data/prompts_sample.txt
  ```

- **Start Automation (Desktop Chrome):**
  ```bash
  python -m app start
  ```

- **Start in Test/Mock Mode (Synthetic Clips, No Chrome Required):**
  ```bash
  python -m app start --mock
  ```

- **Retry a Failed Scene:**
  ```bash
  python -m app retry 23
  ```

---

## 🔐 Google Flow Authentication Workflow

1. On first run, Google Flow Auto opens a persistent browser profile directory (`browser_profile/`).
2. If you are not signed in, the application safely sets its state to **`AUTH_REQUIRED`** and pauses.
3. Log into your Google account manually in the opened browser window.
4. Click **`[RESUME]`** in the Web UI or run `python -m app start` in the terminal.
5. Your login session is saved in the local profile directory for subsequent runs.
6. **No passwords or credentials are ever stored, logged, or transmitted.**

---

## 📁 Output Directory Structure

Generated clips and merged videos are stored deterministically:

```text
output/
├── Video_01/
│   ├── scene_01.mp4
│   ├── scene_02.mp4
│   ├── scene_03.mp4
│   ├── scene_04.mp4
│   ├── scene_05.mp4
│   ├── scene_06.mp4
│   └── Video_01.mp4    ◄── Final 48-second merged video
├── Video_02/
│   ├── scene_01.mp4
│   ...
│   └── Video_02.mp4
...
└── Video_10/
    ├── scene_01.mp4
    ...
    └── Video_10.mp4
```

Individual source scene clips are preserved and never automatically deleted.

---

## 💾 Checkpoint & Crash Recovery

Progress is continuously persisted in SQLite (`data/google_flow_auto.db`):
- If the application terminates after **Scene 37**, restarting the application will automatically resume from **Scene 38**.
- Completed scenes whose files exist and pass validation are never re-generated.
- If a crash occurs mid-generation or mid-download, the in-flight scene is reset to `PENDING` with retry tracking.

---

## 🧪 Testing

Run the automated test suite with pytest:

```bash
pytest -v
```

Tests include:
- `test_parser.py`: Blank-line and `VIDEO 01` parsing, 6-divisibility validation.
- `test_checkpoint.py`: Database operations, crash recovery, and resume without re-running.
- `test_merger.py`: End-to-end FFmpeg clip probing and multi-clip concatenation.
- `test_controller.py`: Full asynchronous loop simulation using `MockFlowBot`.

---

## ⚠️ Limitations & Disclaimers

- **UI Dependency:** This tool uses browser automation to interact with the web interface of Google Flow. If Google alters its web DOM or user interface, update selectors in [`app/flow/selectors.py`](file:///app/flow/selectors.py).
- **Unofficial Utility:** This project is an independent open-source automation utility and is not affiliated with, endorsed by, or sponsored by Google.

---

## 📄 License

Distributed under the [MIT License](LICENSE).
