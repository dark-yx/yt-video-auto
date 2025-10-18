
import google.generativeai as genai
from src.config import GOOGLE_API_KEY
from typing import List

genai.configure(api_key=GOOGLE_API_KEY)

def generate_lyrics(prompt: str, song_style: str, num_songs: int) -> List[str]:
    """
    Genera una lista de letras de canciones utilizando la API de Gemini.
    """
    print(f"Generando {num_songs} conjunto(s) de letras con el estilo: {song_style}")
    lyrics_list = []
    model = genai.GenerativeModel('gemini-pro')
    
    for i in range(num_songs):
        try:
            final_prompt = (
                f"Escribe una canción completa sobre el tema: '{prompt}'."
                f"El estilo musical debe ser '{song_style}'."
                f"La canción debe tener una estructura clara con secciones como [Estrofa], [Estribillo], y [Puente]."
            )
            if num_songs > 1:
                final_prompt += f" Esta es la canción {i + 1} de un total de {num_songs} para un proyecto de video musical."

            response = model.generate_content(final_prompt)
            lyrics_list.append(response.text)
            print(f"Letras generadas para la canción {i + 1}")
        except Exception as e:
            print(f"Error al generar las letras para la canción {i + 1}: {e}")
            # Añadimos un marcador de posición para no romper el flujo
            lyrics_list.append("[Letras no generadas por un error]")
            
    return lyrics_list
