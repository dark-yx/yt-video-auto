
import os
import sys
import time
import httplib2
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

from src.config import CLIENT_SECRETS_FILE

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

def get_authenticated_service():
    """Autentica al usuario y devuelve un objeto de servicio de YouTube listo para usar."""
    credential_path = os.path.join('./', 'youtube-credentials.json')
    storage = Storage(credential_path)
    credentials = storage.get()
    
    if not credentials or credentials.invalid:
        flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                                       scope=YOUTUBE_UPLOAD_SCOPE,
                                       message="Revise el README para obtener instrucciones de autenticación.")
        class Args:
            auth_host_name = 'localhost'
            noauth_local_webserver = False
            auth_host_port = [8080, 8090]
            logging_level = 'ERROR'
        
        credentials = run_flow(flow, storage, Args())
        print("Almacenando credenciales en " + credential_path)

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, http=credentials.authorize(httplib2.Http()))

def resumable_upload(insert_request, update_callback, task_instance):
    """
    Maneja la carga reanudable, informa el progreso y devuelve el ID del video.
    """
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            progress_msg = "Cargando el archivo a YouTube..."
            print(progress_msg)
            # Actualizar el estado de Celery
            task_instance.update_state(
                state='PROGRESS',
                meta={'details': progress_msg, 'progress': '95%'}
            )
            
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    video_id = response['id']
                    print(f"Video subido con éxito con ID: {video_id}")
                    return video_id
                else:
                    print("La carga falló con una respuesta inesperada: %s" % response)
                    return None
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                error = f"Se produjo un error recuperable del servidor: {e}"
            else:
                print(f"Ocurrió un error de HTTP no recuperable: {e.resp.status} {e.content}")
                raise
        except Exception as e:
            error = f"Se produjo un error no recuperable durante la carga: {e}"
            print(error)
            raise

        if error is not None:
            print(error)
            retry += 1
            if retry > 5:
                print("No se pudo completar la carga después de varios reintentos.")
                return None
            
            sleep_time = 2 ** retry
            print(f"Reintentando en {sleep_time} segundos...")
            time.sleep(sleep_time)
            
def upload_video_to_youtube(video_path, title, description, tags, update_callback, task_instance, privacy_status="private"):
    """
    Carga un video en YouTube y devuelve la URL completa del video.
    """
    print(f"Iniciando la carga a YouTube del video: {video_path}")
    try:
        youtube = get_authenticated_service()
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags.split(",") if isinstance(tags, str) else tags,
                "categoryId": "10"  # 10 es la categoría de "Música"
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }

        insert_request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
        )

        video_id = resumable_upload(insert_request, update_callback, task_instance)
        
        if video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"URL del video: {video_url}")
            return video_url
        else:
            print("La carga a YouTube no devolvió un ID de video.")
            return None

    except Exception as e:
        print(f"Ocurrió un error durante la carga a YouTube: {e}")
        # En caso de un error catastrófico, lo relanzamos para que Celery lo marque como FAILURE
        raise

