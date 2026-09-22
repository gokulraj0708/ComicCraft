# Run ComicCraft on Android with Spck Editor + Termux

## Important

Spck Editor can edit the project, but its normal HTML preview cannot execute a Python FastAPI server. Keep the project in shared storage so Spck can edit it, and run the server from Termux. Open the running site in Chrome or another browser.

Use **demo stories + placeholder images first**. Do not install local Stable Diffusion on a normal phone.

## 1. Extract and open the project

1. Extract `ComicCraft-complete.zip` with Android Files or ZArchiver.
2. Move the `ComicCraft` folder to:

```text
Internal storage/Documents/ComicCraft
```

3. In Spck, choose **Open Folder**, select `Documents/ComicCraft`, and grant access.

## 2. Prepare Termux

Open Termux and run:

```bash
termux-setup-storage
pkg update -y
pkg upgrade -y
pkg install -y python python-pillow git rust clang make pkg-config libjpeg-turbo libpng freetype
```

Accept Android's storage permission when requested.

## 3. Install ComicCraft

```bash
cd ~/storage/shared/Documents/ComicCraft
bash android-setup.sh
```

The virtual environment is intentionally created under Termux's home directory, not shared storage. Android shared storage can cause executable and symlink problems for a virtual environment.

## 4. Run

```bash
cd ~/storage/shared/Documents/ComicCraft
bash android-run.sh
```

Keep Termux open. In your browser visit:

```text
http://127.0.0.1:8000
```

Spck's preview button is not used for this Python application.

## 5. Stop and restart

Stop the server in Termux with **Ctrl+C**.

Restart later:

```bash
cd ~/storage/shared/Documents/ComicCraft
bash android-run.sh
```

If Android stops the process while the screen is off, run `termux-wake-lock` before starting the server and `termux-wake-unlock` when finished.

## 6. Enable real Gemini stories (optional)

Install the mobile-optional SDK:

```bash
source ~/.venvs/comiccraft/bin/activate
pip install "google-genai>=1,<3"
```

In Spck, open `.env` and set:

```dotenv
AI_MODE=gemini
GEMINI_API_KEY=your_key_here
GEMINI_OUTLINE_MODEL=gemini-3.5-flash-lite
GEMINI_STORY_MODEL=gemini-3.5-flash
GEMINI_OUTLINE_FALLBACK_MODELS=gemini-flash-lite-latest,gemini-3.5-flash
GEMINI_STORY_FALLBACK_MODELS=gemini-flash-latest,gemini-3.6-flash
GEMINI_RETRY_ATTEMPTS=3
GEMINI_RETRY_BASE_SECONDS=1.5
GEMINI_RETRY_MAX_SECONDS=8
IMAGE_PROVIDER=placeholder
ALLOW_AI_FALLBACK=true
```

Restart the server. This is the recommended mobile configuration: Gemini writes the story while the phone creates lightweight placeholder panel art.

## 7. Hosted AI images (optional)

Local Diffusers is too heavy for most phones. Hosted Hugging Face image generation does not use the phone's GPU:

```bash
source ~/.venvs/comiccraft/bin/activate
pip install "huggingface-hub>=0.28,<2"
```

Then update `.env`:

```dotenv
IMAGE_PROVIDER=huggingface
HF_TOKEN=hf_your_token_here
HF_MODEL=stabilityai/stable-diffusion-xl-base-1.0
ALLOW_IMAGE_FALLBACK=true
```

Provider access may require credits. If it fails, ComicCraft displays labeled placeholder panels.

## 8. Test on Android

```bash
source ~/.venvs/comiccraft/bin/activate
cd ~/storage/shared/Documents/ComicCraft
pip install pytest
python -m pytest
```

Also test these URLs in the browser:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Installation troubleshooting

### Pillow fails

Install Termux's build dependencies and retry:

```bash
pkg install -y python-pillow clang make pkg-config libjpeg-turbo libpng freetype
source ~/.venvs/comiccraft/bin/activate
pip install --no-cache-dir Pillow
```

### Pydantic installation asks for Rust

```bash
pkg install -y rust clang
source ~/.venvs/comiccraft/bin/activate
pip install --no-cache-dir pydantic pydantic-core
```

### Folder is not found

Run `termux-setup-storage` again and verify that this command lists the project:

```bash
ls ~/storage/shared/Documents/ComicCraft
```

If you extracted it into Download instead, use:

```bash
cd ~/storage/downloads/ComicCraft
```
