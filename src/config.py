
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SUNO_COOKIE = os.getenv("SUNO_COOKIE")

if not GOOGLE_API_KEY:
    raise ValueError("No se encontró la clave API de Google. Asegúrese de que su archivo .env esté configurado correctamente.")

if not SUNO_COOKIE:
    raise ValueError("No se encontró la cookie de Suno. Asegúrese de que su archivo .env esté configurado correctamente.")

CLIPS_DIR = "src/clips"
SONGS_DIR = "src/songs"
OUTPUT_DIR = "src/output"
VIDEO_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "final_video.mp4")
CLIENT_SECRETS_FILE = "client_secrets.json"
