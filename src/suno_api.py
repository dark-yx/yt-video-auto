import requests
import uuid
import time
import os
import re
from src.config import SUNO_COOKIE

class SunoApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.device_id = str(uuid.uuid4())
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0",
            "device-id": self.device_id
        })
        # Restaurado: Leer la cookie desde el archivo .env
        self._set_cookies_from_string(SUNO_COOKIE)
        self.auth_token = None
        self.session_id = None # Nueva propiedad para el ID de sesión
        self.clerk_base_url = "https://clerk.suno.com/v1"
        self.api_base_url = "https://studio-api.prod.suno.com/api"

    def _set_cookies_from_string(self, cookie_string):
        if not cookie_string:
            return
        for cookie in cookie_string.split(';'):
            cookie = cookie.strip()
            if not cookie:
                continue
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                self.session.cookies.set(name, value)
            else:
                self.session.cookies.set(cookie, None)

    def _get_session_token(self):
        response = self.session.get(f"{self.clerk_base_url}/client?__clerk_api_version=2025-04-10&_clerk_js_version=5.102.0")
        response.raise_for_status()
        data = response.json()
        jwt_token = data.get("response", {}).get("sessions", [{}])[0].get("last_active_token", {}).get("jwt")
        if not jwt_token:
            raise Exception("No se pudo obtener el token JWT de Clerk.")
        self.auth_token = jwt_token
        self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
        return jwt_token

    def initialize_session(self):
        """Realiza la autenticación completa de dos pasos."""
        print("Iniciando autenticación de sesión de dos pasos...")
        # Paso 1: Obtener el token JWT
        self._get_session_token()
        print("Paso 1/2: Token JWT obtenido.")

        # Paso 2: Usar el token JWT para obtener un session_id de la API de Suno
        session_response = self.session.get(f"{self.api_base_url}/user/get_user_session_id/")
        session_response.raise_for_status()
        
        data = session_response.json()
        session_id = data.get('session_id')

        if not session_id:
            raise Exception("No se pudo obtener el session-id de la API de Suno.")
        
        self.session_id = session_id
        print(f"Paso 2/2: session-id obtenido: {session_id}")
        print("Autenticación completada.")

    def check_connection(self):
        if not self.session_id:
            self.initialize_session()
        response = self.session.get(f"{self.api_base_url}/user/get_user_session_id/")
        response.raise_for_status()
        return response.json()

    def generate(self, tags, title, prompt, make_instrumental, vocal_gender='female', mv="chirp-crow"):
        if not self.session_id or not self.auth_token:
            self.initialize_session()
        
        project_id = "d92ff1eb-5aa5-44c8-9066-1ad23f228aaf"

        suno_gender = 'f'
        if str(vocal_gender).lower() == 'male':
            suno_gender = 'm'

        base_payload = {
            "project_id": project_id,
            "generation_type": "TEXT",
            "mv": mv,
            "prompt": prompt,
            "tags": tags,
            "title": title,
            "make_instrumental": make_instrumental,
            "transaction_uuid": str(uuid.uuid4()),
            "token": self.auth_token, # CORREGIDO: Usar el token de autenticación
        }

        if mv == "chirp-crow":
            metadata = {
                "create_mode": "custom",
                "stream": True,
                "priority": 10,
                "control_sliders": {
                    "style_weight": 0.5,
                    "weirdness_constraint": 0.5
                },
                "web_client_pathname": "/create",
                "is_max_mode": False,
                "is_mumble": False,
                "create_session_token": str(uuid.uuid4()),
                "disable_volume_normalization": False,
            }
            if not make_instrumental:
                metadata["vocal_gender"] = suno_gender
        elif mv == "chirp-auk-turbo":
            metadata = {
                "web_client_pathname": "/create",
                "is_max_mode": False,
                "create_mode": "custom",
                "can_control_sliders": ["weirdness_constraint", "style_weight"],
                "create_session_token": str(uuid.uuid4()),
                "disable_volume_normalization": False,
                "user_tier": "4497580c-f4eb-4f86-9f0e-960eb7c48d7d",
            }
            if not make_instrumental:
                metadata["vocal_gender"] = suno_gender
        else:
            raise ValueError(f"Modelo Suno '{mv}' no soportado.")
        
        payload = {**base_payload, "metadata": metadata}
        
        response = self.session.post(f"{self.api_base_url}/generate/v2-web/", json=payload)
        
        if not response.ok:
            error_details = f"Status Code: {response.status_code}"
            try:
                error_details += f" - Body: {response.json()}"
            except ValueError:
                error_details += f" - Body: {response.text}"
            raise Exception(f"Suno API Error: {error_details}")
            
        return response.json()

    def poll_for_song(self, ids):
        if not self.session_id:
            self.initialize_session()
        if isinstance(ids, str):
            ids = [ids]
        endpoint = f"{self.api_base_url}/feed/v2?ids={','.join(ids)}"
        while True:
            response = self.session.get(endpoint)
            response.raise_for_status()
            data = response.json()
            clips = data.get('clips', [])
            if clips and isinstance(clips, list) and all(isinstance(song, dict) and song.get('status') == 'complete' for song in clips):
                return clips
            print("Canción no lista, reintentando en 10 segundos...")
            time.sleep(10)

    def download_song(self, song, output_filename=None):
        """
        Downloads a song using the direct audio_url from the song object,
        writing it to a file as a stream.
        """
        if not self.session_id:
            self.initialize_session()

        audio_url = song.get('audio_url')
        song_title = song.get('title', 'Untitled Song')

        if not audio_url:
            raise Exception(f"El objeto de la canción para '{song_title}' no contenía una 'audio_url'.")

        audio_response = self.session.get(audio_url, stream=True)
        audio_response.raise_for_status()

        if output_filename:
            file_path = os.path.join("songs", output_filename)
        else:
            safe_title = re.sub(r'[\\/*?"<>|]', "", song_title)
            file_path = os.path.join("songs", f"{safe_title}.mp3")

        os.makedirs("songs", exist_ok=True)
        with open(file_path, 'wb') as f:
            for chunk in audio_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Descarga exitosa de '{song_title}' en {file_path}")
        return file_path

if __name__ == "__main__":
    # ... (código de prueba local sin cambios)
    pass