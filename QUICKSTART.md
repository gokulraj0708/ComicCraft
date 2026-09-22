# ComicCraft Quick Start

ComicCraft starts in **demo + placeholder mode**, so it works without API keys.

## Windows

1. Install Python 3.11 or newer from <https://python.org> and enable **Add Python to PATH**.
2. Extract the project ZIP.
3. Open the extracted `ComicCraft` folder in a terminal.
4. Run:

```bat
setup.bat
run.bat
```

5. Open <http://127.0.0.1:8000>.

## macOS / Linux

```bash
cd ComicCraft
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

Open <http://127.0.0.1:8000>.

## Android with Spck Editor

Spck is used to edit; Termux runs FastAPI:

```bash
termux-setup-storage
pkg update -y
pkg install -y python python-pillow git rust clang make pkg-config libjpeg-turbo libpng freetype
cd ~/storage/shared/Documents/ComicCraft
bash android-setup.sh
bash android-run.sh
```

Open <http://127.0.0.1:8000>. Read `ANDROID-SPCK.md` for the full mobile guide.

## Enable real Gemini stories

Open `.env`, set:

```dotenv
AI_MODE=gemini
GEMINI_API_KEY=your_key_here
```

Restart the server. The model names are configurable in the same file.

## Enable hosted AI images

Open `.env`, set:

```dotenv
IMAGE_PROVIDER=huggingface
HF_TOKEN=hf_your_token_here
HF_MODEL=stabilityai/stable-diffusion-xl-base-1.0
```

Restart the server. Provider/model access and charges depend on your Hugging Face account.

## Run tests

```bash
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pytest
```

Useful pages:

- App: <http://127.0.0.1:8000>
- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>
