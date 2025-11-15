import os
import re
from src.suno_api import SunoApiClient
from src.config import SONGS_DIR
from celery import Task

def create_and_download_song(client: SunoApiClient, lyrics: str, song_style: str, song_title: str, vocal_gender: str = 'f', is_instrumental: bool = False, task_instance: Task = None, suno_model: str = "chirp-crow") -> list[str]:
    """
    Generates two songs with the new SunoApiClient, reports progress, and downloads them.
    Returns a list with the file paths of the downloaded songs.
    """
    progress_msg = f"Enviando solicitud para '{song_title}' a SunoApiClient y esperando la generación..."
    print(progress_msg)
    if task_instance:
        task_instance.update_state(
            state='PROGRESS',
            meta={'details': progress_msg}
        )

    try:
        # El cliente ahora se pasa como argumento, no se crea aquí.

        generation_response = client.generate(
            tags=song_style,
            title=song_title,
            prompt=lyrics,
            make_instrumental=is_instrumental,
            vocal_gender=vocal_gender,
            mv=suno_model
        )

        song_ids = [clip['id'] for clip in generation_response['clips']]
        
        progress_msg = f"Canciones enviadas a generar. Esperando a que finalicen (IDs: { ', '.join(song_ids) })..."
        print(progress_msg)
        if task_instance:
            task_instance.update_state(state='PROGRESS', meta={'details': progress_msg})

        completed_songs = client.poll_for_song(song_ids)

        song_paths = []
        # Ensure we only process up to the number of songs generated (usually 2)
        for i, song in enumerate(completed_songs[:2]):
            # Sanitize the title to create a base for the filename
            safe_title = re.sub(r'[\\/*?"<>|]', "", song['title'])
            # Create the custom filename that the main orchestrator expects (e.g., "1_My_Song.mp3")
            output_filename = f"{i+1}_{safe_title.replace(' ', '_')}.mp3"
            
            print(f"Descargando canción '{song['title']}' como '{output_filename}'...")
            
            file_path = client.download_song(
                song=song,
                output_filename=output_filename
            )
            song_paths.append(file_path)

        print("Canciones descargadas con éxito.")
        return song_paths

    except Exception as e:
        print(f"Error al interactuar con la API de Suno (SunoApiClient): {e}")
        raise