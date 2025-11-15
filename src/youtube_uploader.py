import os
import time
import httplib2
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from celery import Task

from src.config import CLIENT_SECRETS_FILE

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
CREDENTIALS_FILE = os.path.join(os.getcwd(), 'youtube-credentials.json')

# --- Funciones para el Flujo de Autenticación Web (OAuth2) ---

def get_auth_flow():
    """Crea y devuelve un objeto de flujo OAuth2."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise FileNotFoundError(
            f"El archivo de secretos de cliente '{CLIENT_SECRETS_FILE}' no se encontró. "
            "Asegúrate de que esté en la raíz del proyecto."
        )
    # El redirect_uri debe coincidir exactamente con el que configuraste en Google Cloud Console
    return flow_from_clientsecrets(
        CLIENT_SECRETS_FILE, 
        scope=YOUTUBE_UPLOAD_SCOPE,
        redirect_uri='http://127.0.0.1:8000/oauth2callback'
    )

def exchange_code_for_credentials(code: str):
    """
    Intercambia un código de autorización por credenciales y las guarda en el archivo.
    """
    flow = get_auth_flow()
    credentials = flow.step2_exchange(code)
    storage = Storage(CREDENTIALS_FILE)
    storage.put(credentials)
    return credentials

# --- Función Principal para el Servicio Autenticado ---

def get_authenticated_service():
    """
    Obtiene el objeto de servicio de la API de YouTube autenticado.
    Asume que 'youtube-credentials.json' ya existe y es válido.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        # Este error ahora le indica al frontend que debe iniciar el flujo de autenticación.
        raise FileNotFoundError("No se encontraron credenciales de YouTube. Por favor, autoriza la aplicación primero.")

    storage = Storage(CREDENTIALS_FILE)
    credentials = storage.get()

    if not credentials or credentials.invalid:
        raise Exception("Las credenciales de YouTube son inválidas o han expirado. Por favor, re-autoriza la aplicación.")

    return build(
        YOUTUBE_API_SERVICE_NAME, 
        YOUTUBE_API_VERSION, 
        http=credentials.authorize(httplib2.Http())
    )

# --- Lógica de Subida de Video (sin cambios) ---

def resumable_upload(insert_request, task_instance: Task):
    response = None
    error = None
    retry = 0
    MAX_RETRIES = 5

    while response is None:
        try:
            if task_instance:
                task_instance.update_state(state='PROGRESS', meta={'details': 'Subiendo archivo a YouTube...', 'progress': '95%'})
            
            status, response = insert_request.next_chunk()
            if response and 'id' in response:
                return response['id']

        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                error = f'Error recuperable del servidor (intento {retry + 1}/{MAX_RETRIES}): {e}'
            else:
                raise HttpError(f"Error HTTP no recuperable: {e}", e.resp)
        except Exception as e:
            raise IOError(f"Error durante la subida del archivo: {e}")
        
        if error:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                raise RuntimeError("Se superó el número máximo de reintentos para la subida a YouTube.")
            time.sleep((2 ** retry) + 1)

def upload_video_to_youtube(video_path: str, title: str, description: str, tags: list, task_instance: Task, privacy_status="private") -> str:
    """
    Sube un video a YouTube usando una subida resumible.
    """
    try:
        youtube = get_authenticated_service()
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "10" # Música
            },
            "status": {"privacyStatus": privacy_status}
        }

        insert_request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
        )

        video_id = resumable_upload(insert_request, task_instance)
        
        if video_id:
            print(f"Video subido con éxito. ID: {video_id}")
            return f"https://www.youtube.com/watch?v={video_id}"
        else:
            raise RuntimeError("La carga a YouTube finalizó pero no devolvió un ID de video.")
            
    except Exception as e:
        print(f"Error durante la carga a YouTube: {e}")
        raise