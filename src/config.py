
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUNO_COOKIE = os.getenv("SUNO_COOKIE")

if not OPENAI_API_KEY:
    raise ValueError("No se encontró la clave API de OpenAI. Asegúrese de que su archivo .env esté configurado correctamente.")

if not GROQ_API_KEY:
    raise ValueError("No se encontró la clave API de Groq. Asegúrese de que su archivo .env esté configurado correctamente.")

if not SUNO_COOKIE:
    raise ValueError("No se encontró la cookie de Suno. Asegúrese de que su archivo .env esté configurado correctamente.")

# Rutas corregidas para apuntar a la raíz del proyecto
CLIPS_DIR = "clips"
SONGS_DIR = "songs"
OUTPUT_DIR = "output"
METADATA_DIR = "metadata"
LYRICS_DIR = "lyrics"
PUBLICATION_REPORTS_DIR = "publication_reports"

# Asegurarse de que el path del video de salida sea único para evitar sobreescrituras
VIDEO_OUTPUT_FILENAME = "final_video.mp4" # Se puede hacer más dinámico si es necesario
VIDEO_OUTPUT_PATH = os.path.join(OUTPUT_DIR, VIDEO_OUTPUT_FILENAME)

CLIENT_SECRETS_FILE = "client_secrets.json"
