import openai
from src.config import OPENAI_API_KEY
from typing import List

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def generate_lyrics_for_song(prompt: str, song_style: str, language: str = "spanish", gender: str = "Masculino", song_index: int = 1, total_songs: int = 1) -> str:
    """
    Genera la letra y tags para una única canción.
    """
    try:
        system_prompt = (
            f"Eres un experto compositor y musicólogo. Tu tarea es escribir una canción completa y, por separado, detallar su estilo musical."
            f"La letra y el título de la canción deben estar en '{language}'."
            f"Para los TAGS, tu tarea es describir el estilo musical '{song_style}' en INGLÉS. No describas la letra que acabas de crear. No menciones el tema de la canción ni su título."
            f"La descripción de los TAGS debe ser puramente musical, enfocada en la instrumentación, el tempo, la atmósfera, la estructura y los elementos sonoros típicos del estilo '{song_style}'."
            f"El género del cantante es '{gender}'. Debes reflejar esto en la descripción de los TAGS (ej. 'powerful masculine vocals' o 'powerful feminine vocals')."
            "Debes estructurar tu respuesta EXACTAMENTE de la siguiente manera, sin texto adicional antes o después:"
            "\n\nTITLE: [El título de la canción aquí]"
            "\n\nPROMPT:"
            "\n[Letra completa de la canción, siguiendo ESTRICTAMENTE esta estructura: Intro, Verse 1 (8 líneas), Pre-Chorus, Chorus (repetido 2 veces), Verse 2 (8 líneas), Pre-Chorus, Chorus (repetido 2 veces), Bridge, Outro]"
            "\n\nTAGS:"
            "\n[Un único párrafo en INGLÉS de 500 a 1000 caracteres que describa únicamente el estilo musical '{song_style}', su instrumentación, tempo, y ambiente, mencionando el estilo vocal pero sin hacer referencia a la letra o tema de la canción.]"
            "\n\nGENERO: [Aquí 'Masculino' o 'Femenino']"
        )
        user_prompt = (
            f"Tema de la canción: '{prompt}'\n"
            f"Estilo musical general: '{song_style}'\n"
            f"Género del cantante: '{gender}'"
        )
        if total_songs > 1:
            user_prompt += f"\nEsta es la canción {song_index} de un total de {total_songs}."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error al generar las letras para la canción {song_index} con OpenAI: {e}")
        return "TITLE: Error\nPROMPT: [Letras no generadas por un error]\nTAGS: error"

def generate_instrumental_prompt_for_song(prompt: str, song_style: str, language: str = "spanish", song_index: int = 1, total_songs: int = 1) -> str:
    """
    Genera un prompt para una única canción instrumental (título y tags).
    """
    try:
        system_prompt = (
            f"Eres un experto musicólogo. Tu tarea es crear un título para una canción instrumental y describir su estilo musical."
            f"El título de la canción debe estar en '{language}'."
            f"Para los TAGS, tu tarea es describir el estilo musical '{song_style}' en INGLÉS. No menciones el tema de la canción ni su título."
            f"La descripción de los TAGS debe ser puramente musical, enfocada en la instrumentación, el tempo, la atmósfera, la estructura y los elementos sonoros típicos del estilo '{song_style}'."
            "Debes estructurar tu respuesta EXACTAMENTE de la siguiente manera, sin texto adicional antes o después:"
            "\n\nTITLE: [El título de la canción aquí]"
            "\n\nTAGS:"
            "\n[Un único párrafo en INGLÉS de 500 a 1000 caracteres que describa únicamente el estilo musical '{song_style}', su instrumentación, tempo, y ambiente, sin hacer referencia al tema de la canción.]"
        )
        user_prompt = (
            f"Tema de la canción: '{prompt}'\n"
            f"Estilo musical general: '{song_style}'"
        )
        if total_songs > 1:
            user_prompt += f"\nEsta es la canción {song_index} de un total de {total_songs}."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error al generar el prompt instrumental para la canción {song_index}: {e}")
        return "TITLE: Error\nTAGS: error"