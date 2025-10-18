
import os
from suno import Suno, Song
from src.config import SUNO_COOKIE, SONGS_DIR
from celery import Task

def create_and_download_song(lyrics: str, song_style: str, song_title: str, task_instance: Task = None) -> str:
    """
    Genera una canción con la API de Suno, informa del progreso y la descarga.
    Devuelve la ruta del archivo de la canción descargada.
    """
    progress_msg = f"Enviando solicitud para '{song_title}' a la IA de Suno y esperando la generación..."
    print(progress_msg)
    if task_instance:
        # Obtenemos el progreso actual para no retroceder
        current_progress = int(task_instance.info.get('progress', '0').replace('%', ''))
        task_instance.update_state(
            state='PROGRESS',
            meta={'details': progress_msg, 'progress': f'{current_progress}%'} # Mantenemos el progreso
        )

    try:
        client = Suno(cookie=SUNO_COOKIE)
        songs: list[Song] = client.generate(
            prompt=lyrics,
            is_custom=True,
            tags=song_style,
            title=song_title,
            wait_for_song=True, # Esta es una llamada de bloqueo
        )

        song = songs[0]
        # Asegurarse de que el nombre del archivo sea seguro para el sistema de archivos
        safe_title = "".join(c for c in song_title if c.isalnum() or c in (' ', '-')).rstrip()
        song_path = os.path.join(SONGS_DIR, f"{safe_title.replace(' ', '_')}.mp3") # Cambiado a mp3, ya que es audio
        
        print(f"Descargando canción '{song_title}' en: {song_path}")
        song.download(save_path=song_path)

        print(f"Canción descargada con éxito.")
        return song_path
    except Exception as e:
        print(f"Error al interactuar con la API de Suno: {e}")
        # Es importante relanzar la excepción para que la tarea de Celery falle
        raise
