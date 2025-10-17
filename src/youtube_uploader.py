
import os
import sys
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

# Esta función se basa directamente en la muestra oficial de Google
def get_authenticated_service():
    """Autentica al usuario y devuelve un objeto de servicio de YouTube listo para usar."""
    credential_path = os.path.join('./', 'youtube-credentials.json')
    storage = Storage(credential_path)
    credentials = storage.get()
    
    if not credentials or credentials.invalid:
        flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                                       scope=YOUTUBE_UPLOAD_SCOPE,
                                       message="Revise el README para obtener instrucciones de autenticación.")

        # La biblioteca oauth2client en sí no tiene un `argparser` global
        # En su lugar, pase un objeto `args` mínimo
        class Args:
            auth_host_name = 'localhost'
            noauth_local_webserver = False
            auth_host_port = [8080, 8090]
            logging_level = 'ERROR'
        
        credentials = run_flow(flow, storage, Args())
        print("Almacenando credenciales en " + credential_path)

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, http=credentials.authorize(httplib2.Http()))

def upload_video_to_youtube(video_path, title, description, tags, privacy_status="private"):
    """
    Carga un video en YouTube con los metadatos proporcionados.
    """
    print(f"Iniciando la carga a YouTube del video: {video_path}")
    try:
        youtube = get_authenticated_service()
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags.split(","),
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

        resumable_upload(insert_request)

    except HttpError as e:
        print(f"Ocurrió un error de HTTP: {e.resp.status} {e.content}")
    except Exception as e:
        print(f"Ocurrió un error durante la carga: {e}")

# Función auxiliar de carga reanudable del ejemplo de Google
def resumable_upload(insert_request):
    """Maneja la carga reanudable y reintentos."""
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print("Cargando el archivo...")
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print(f"Video subido con éxito con ID: {response['id']}")
                else:
                    exit("La carga falló con una respuesta inesperada: %s" % response)
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                error = "Se produjo un error recuperable del servidor: %s" % e
            else:
                raise
        except Exception as e:
            error = f"Se produjo un error no recuperable: {e}"

        if error is not None:
            print(error)
            retry += 1
            if retry > 5:
                exit("No se pudo completar la carga después de varios reintentos.")
            print(f"Reintentando en {2 ** retry} segundos...")
            time.sleep(2 ** retry)
