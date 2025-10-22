
import openai
from src.config import OPENAI_API_KEY
from typing import List

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def generate_lyrics(prompt: str, song_style: str, num_songs: int) -> List[str]:
    """
    Genera una lista de letras de canciones utilizando la API de OpenAI.
    """
    print(f"Generando {num_songs} conjunto(s) de letras con el estilo: {song_style} usando gpt-4o-mini")
    lyrics_list = []
    
    for i in range(num_songs):
        try:
            system_prompt = (
                "Eres un experto compositor de canciones. Escribe una canción completa basada en el tema y estilo proporcionados. "
                "La canción debe tener una estructura clara con secciones como [Estrofa], [Estribillo], y opcionalmente [Puente], [Intro] o [Outro]."
            )
            user_prompt = (
                f"Tema de la canción: '{prompt}'\n"
                f"Estilo musical: '{song_style}'"
            )
            if num_songs > 1:
                user_prompt += f"\nEsta es la canción {i + 1} de un total de {num_songs} para un proyecto de video musical."

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
            )
            
            generated_lyrics = response.choices[0].message.content
            lyrics_list.append(generated_lyrics)
            print(f"Letras generadas para la canción {i + 1}")
        except Exception as e:
            print(f"Error al generar las letras para la canción {i + 1} con OpenAI: {e}")
            # Añadimos un marcador de posición para no romper el flujo
            lyrics_list.append("[Letras no generadas por un error]")
            
    return lyrics_list
