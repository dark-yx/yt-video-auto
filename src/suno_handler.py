
import os
from suno import Suno, Song
from src.config import SUNO_COOKIE, SONGS_DIR

def create_and_download_song(lyrics: str, song_style: str, song_title: str) -> str:
    """
    Genera una canción con la API de Suno y la descarga.
    Devuelve la ruta del archivo de la canción descargada.
    """
    print(f"Generando la canción '{song_title}' con Suno...")
    try:
        client = Suno(cookie=SUNO_COOKIE)
        songs: list[Song] = client.generate(
            prompt=lyrics,
            is_custom=True,  # Necesario para letras personalizadas
            tags=song_style,
            title=song_title,
            wait_for_song=True, # Espera a que se complete la generación
        )

        # Descargar la primera canción generada
        song = songs[0]
        song_path = os.path.join(SONGS_DIR, f"{song_title.replace(' ', '_')}.mp4")
        song.download(save_path=song_path)

        print(f"Canción descargada en: {song_path}")
        return song_path
    except Exception as e:
        print(f"Error al interactuar con la API de Suno: {e}")
        return ""
