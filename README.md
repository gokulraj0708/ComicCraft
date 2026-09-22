# ComicCraft — AI Comic Story Creator

A complete FastAPI application that turns a story idea into a structured comic, generates panel artwork through a selectable provider, previews the result in a responsive web UI, and exports a downloadable PDF.

The project is based on the supplied ComicCraft documentation but replaces incomplete and fragile snippets with validated, runnable modules.

## Features

- Browser form with story, character, setting, tone, style, and 3–8 panels
- Two-stage Gemini workflow: structured outline, then structured comic script
- Strict Pydantic validation instead of splitting free-form AI text
- Three image modes:
  - `placeholder`: fast local demo images; no key or GPU required
  - `huggingface`: hosted text-to-image inference
  - `diffusers`: local Stable Diffusion, loaded only when selected
- Automatic, visible provider fallbacks
- Responsive Jinja2 frontend
- JSON API and interactive OpenAPI documentation
- UUID-isolated output folders and reusable JSON manifests
- Unicode-capable PDF export using bundled DejaVu fonts
- Automated tests, Docker files, cleanup utility, setup scripts, and VS Code configuration

## Project structure

```text
ComicCraft/
├── app/
│   ├── main.py                 # FastAPI factory and middleware
│   ├── routes.py               # Web and JSON routes
│   ├── config.py               # .env configuration
│   ├── schemas.py              # Request, AI-output, and response schemas
│   ├── exceptions.py
│   ├── dependencies.py
│   ├── services/
│   │   ├── comic_service.py    # End-to-end orchestration
│   │   ├── llm.py              # Gemini and demo story providers
│   │   ├── images.py           # Placeholder, HF, and Diffusers providers
│   │   ├── pdf_service.py      # PDF layout/export
│   │   └── repository.py       # Safe filesystem storage
│   ├── templates/              # Jinja2 pages
│   └── static/                 # CSS, JS, icon, and PDF fonts
├── tests/
├── scripts/cleanup.py
├── storage/
├── .env.example
├── requirements*.txt
├── Dockerfile
├── docker-compose.yml
├── setup.sh / setup.bat
└── run.sh / run.bat
```

## Fastest setup: no API keys

### Requirements

- Python 3.11 or newer
- About 250 MB for the normal Python environment
- More storage/GPU memory only if using local Stable Diffusion

### Windows

```bat
setup.bat
run.bat
```

### macOS or Linux

```bash
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

Open <http://127.0.0.1:8000>. The default `AI_MODE=auto` selects the offline demo writer when no Gemini key exists, and `IMAGE_PROVIDER=placeholder` creates local demo panel art.

### Manual installation

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env          # Windows: copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Editor setup

### VS Code

1. Open the `ComicCraft` folder, not its parent folder.
2. Install the recommended Python, Pylance, Ruff, and Docker extensions when prompted.
3. Run `setup.bat` on Windows or `./setup.sh` on macOS/Linux.
4. Select the interpreter inside `.venv` if VS Code does not select it automatically.
5. Press **F5** and choose **ComicCraft: FastAPI**, or run the **Run ComicCraft** task.
6. Run tests from the Testing sidebar or with `python -m pytest`.

The included `.vscode` folder contains launch, task, test, and formatting settings.

### Spck Editor on Android

Spck edits the files, while Termux runs the Python/FastAPI server. Extract the project to `Internal storage/Documents/ComicCraft`, open that folder in Spck, and run these commands in Termux:

```bash
termux-setup-storage
pkg update -y
pkg install -y python python-pillow git rust clang make pkg-config libjpeg-turbo libpng freetype
cd ~/storage/shared/Documents/ComicCraft
bash android-setup.sh
bash android-run.sh
```

Open <http://127.0.0.1:8000> in the Android browser. The mobile script keeps the virtual environment under Termux's home directory because shared storage is not a reliable place for executable virtual-environment files.

Use demo/placeholder mode first. Local Diffusers is not practical on most phones. See **`ANDROID-SPCK.md`** for live Gemini setup, hosted AI images, testing, restarting, and troubleshooting.

## Live Gemini story generation

1. Create a Gemini API key in Google AI Studio.
2. Edit `.env`:

```dotenv
AI_MODE=gemini
GEMINI_API_KEY=your_real_key
GEMINI_OUTLINE_MODEL=gemini-3.5-flash-lite
GEMINI_STORY_MODEL=gemini-3.5-flash
GEMINI_OUTLINE_FALLBACK_MODELS=gemini-flash-lite-latest,gemini-3.5-flash
GEMINI_STORY_FALLBACK_MODELS=gemini-flash-latest,gemini-3.6-flash
GEMINI_RETRY_ATTEMPTS=3
GEMINI_RETRY_BASE_SECONDS=1.5
GEMINI_RETRY_MAX_SECONDS=8
ALLOW_AI_FALLBACK=true
```

3. Restart the server.

The Gemini client now retries transient 429/5xx failures with exponential backoff, switches to configured fallback models, and finally falls back to the deterministic demo story when `ALLOW_AI_FALLBACK=true`. Model availability, free-tier access, and pricing vary by account. Never commit `.env`.

## AI image choices

### A. Placeholder art — default and free

```dotenv
IMAGE_PROVIDER=placeholder
```

This is deterministic local artwork intended for setup, testing, and API demos. It is not presented as model-generated imagery.

### B. Hugging Face hosted generation

```dotenv
IMAGE_PROVIDER=huggingface
HF_TOKEN=hf_your_token
HF_MODEL=stabilityai/stable-diffusion-xl-base-1.0
HF_PROVIDER=
ALLOW_IMAGE_FALLBACK=true
```

The `huggingface_hub.InferenceClient.text_to_image` API is used. Set `HF_PROVIDER` only when your routed provider requires it. Model/provider availability and billing depend on your account. When fallback is enabled, failed panels become labeled placeholder images rather than losing the whole comic.

### C. Local Stable Diffusion

Install the normal requirements first. For NVIDIA, install the correct PyTorch build from <https://pytorch.org/get-started/locally/>, then run:

```bash
pip install -r requirements-local-diffusion.txt
```

Configure:

```dotenv
IMAGE_PROVIDER=diffusers
LOCAL_SD_MODEL=stable-diffusion-v1-5/stable-diffusion-v1-5
LOCAL_SD_DEVICE=auto
LOCAL_SD_STEPS=25
```

The first generation downloads model weights and can require several GB. A supported GPU is strongly recommended.

## API

Interactive documentation: <http://127.0.0.1:8000/docs>

### Create a comic

```bash
curl -X POST http://127.0.0.1:8000/api/v1/comics \
  -H "Content-Type: application/json" \
  -d '{
    "story_prompt": "A brave fox follows glowing leaves to a hidden city.",
    "character_name": "Ember",
    "setting": "an enchanted forest",
    "tone": "Adventurous",
    "art_style": "Modern comic book",
    "panel_count": 5
  }'
```

The documentation-compatible `POST /generate-comic/json` route is also available. It accepts the legacy aliases `prompt` and `style`.

### Other routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Creation form |
| POST | `/generate` | Browser form generation |
| GET | `/comics/{id}` | Reopen a saved preview |
| GET | `/download/{id}` | Download PDF |
| GET | `/export-success?comic_id=...` | Export confirmation |
| POST | `/api/v1/comics` | Create comic as JSON |
| GET | `/api/v1/comics/{id}` | Read comic manifest |
| GET | `/test-image?prompt=...` | Test selected image provider |
| GET | `/health` | Health/configuration summary |

## Testing

All tests force demo + placeholder mode and never call paid services:

```bash
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pytest
python -m pytest --cov=app
```

Manual checks:

1. Open `/health`; status should be `ok`.
2. Create a three-panel comic from the web form.
3. Confirm each panel image loads.
4. Download the PDF and inspect all pages.
5. Open `/docs` and call `POST /api/v1/comics`.
6. With live providers enabled, inspect `provider_info` for fallbacks/warnings.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Generated files persist in `./storage`. The default compose configuration uses demo/placeholder mode unless `.env` enables providers.

## Output and cleanup

Every comic is stored at:

```text
storage/comics/<comic-id>/
├── comic.json
├── comic.pdf
└── panels/
```

Remove old output:

```bash
python scripts/cleanup.py --days 7 --dry-run
python scripts/cleanup.py --days 7
```

## Troubleshooting

- **Gemini 401/403:** verify the key, account, region, and model access.
- **Gemini model not found:** update the two model IDs in `.env`.
- **Hugging Face 401/402/503:** verify token, provider, model access, credits, and timeout.
- **Local model is extremely slow:** use a CUDA GPU, lower image size/steps, or select hosted/placeholder mode.
- **Port already used:** run `uvicorn app.main:app --port 8001`.
- **Old `fpdf` conflict:** run `pip uninstall -y fpdf && pip install --force-reinstall fpdf2`.
- **Generated output consumes disk:** use `scripts/cleanup.py` regularly.

## Production checklist

Before exposing this app publicly, add authentication, per-user quotas, rate limiting, a background task queue, a database, object storage, HTTPS, provider cost budgets, audience-appropriate moderation, monitoring, and scheduled cleanup. The current synchronous generation route is intentionally simple and is best for learning or controlled use.

See `PROJECT_ANALYSIS.md` for the documentation review and design decisions.

## License

Application code: MIT. Bundled DejaVu fonts retain their own license in `app/static/fonts/LICENSE-DejaVu.txt`.
