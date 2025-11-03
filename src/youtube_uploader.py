
import os
import time
import httplib2
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow
from celery import Task

from src.config import CLIENT_SECRETS_FILE

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

def get_authenticated_service():
    """
    Obtiene el objeto de servicio de la API de YouTube, manejando la autenticación OAuth2.
    """
    credential_path = os.path.join(os.getcwd(), 'youtube-credentials.json')
    storage = Storage(credential_path)
    credentials = storage.get()

    if not credentials or credentials.invalid:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(
                f"El archivo '{CLIENT_SECRETS_FILE}' no se encontró. "
                "Por favor, descarga tus credenciales de cliente OAuth 2.0 desde Google Cloud Console "
                "y guárdalas en la raíz del proyecto."
            )
        
        # Este es un flujo interactivo. Se requerirá que el usuario copie un enlace en su navegador
        # y pegue un código de autorización en el terminal.
        flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=YOUTUBE_UPLOAD_SCOPE)
        
        class Args:
            auth_host_name = 'localhost'
            noauth_local_webserver = False
            auth_host_port = [8000, 8090]
            logging_level = 'ERROR'
        
        print("\n--- INICIO DE AUTENTICACIÓN DE YOUTUBE ---")
        print("Se requiere tu intervención para autorizar la subida de videos.")
        print("Por favor, sigue las instrucciones en el terminal.")
        
        credentials = run_flow(flow, storage, Args())
        
        print("--- AUTENTICACIÓN DE YOUTUBE COMPLETADA ---\n")

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, http=credentials.authorize(httplib2.Http()))

def resumable_upload(insert_request, task_instance: Task):
    """Maneja la lógica de subida resumible y los reintentos."""
    response = None
    error = None
    retry = 0
    MAX_RETRIES = 5

    while response is None:
        try:
            if task_instance:
                # El progreso se mantiene estático durante la subida
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
            time.sleep((2 ** retry) + 1) # Backoff exponencial

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
                "categoryId": "10" # Categoría 10 es "Música"
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
        # Relanzamos la excepción para que la tarea de Celery falle
        raise
