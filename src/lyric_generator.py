import openai
from groq import Groq
from src.config import OPENAI_API_KEY, GROQ_API_KEY
from typing import List

# Initialize clients for both services
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

def generate_lyrics_for_song(
    prompt: str, 
    song_style: str, 
    language: str = "spanish", 
    gender: str = "Masculino", 
    song_index: int = 1, 
    total_songs: int = 1,
    llm_model: str = "openai/gpt-4o-mini"
) -> str:
    """
    Genera la letra y tags para una única canción, usando el modelo de lenguaje especificado.
    """
    system_prompt = (
        f"Eres un experto compositor y musicólogo. Tu tarea es escribir una canción completa y, por separado, detallar su estilo musical."
        f"La letra y el título de la canción deben estar en '{language}'."
        f"Para los TAGS, tu tarea es describir el estilo musical '{song_style}' en INGLÉS. No describas la letra que acabas de crear. No menciones el tema de la canción ni su título."
        f"La descripción de los TAGS debe ser puramente musical, enfocada en la instrumentación, el tempo, la atmósfera, la estructura y los elementos sonoros típicos del estilo '{song_style}'."
        f"El género del cantante es '{gender}'. Debes reflejar esto en la descripción de los TAGS (ej. 'powerful masculine vocals' o 'powerful feminine vocals')."
        "Debes estructurar tu respuesta EXACTAMENTE de la siguiente manera, sin texto adicional antes o después:"
        "\n\nTITLE: [El título de la canción aquí]"
        "\n\nPROMPT:"
        "\nIntro:"
        "\n[4 líneas de la introducción]"
        "\n\nVerse 1:"
        "\n[8 líneas de la primera estrofa]"
        "\n\nPre-Chorus:"
        "\n[4 líneas del pre-estribillo]"
        "\n\nChorus:"
        "\n[4 líneas del estribillo]"
        "\n\nChorus:"
        "\n[4 líneas del estribillo repetido, cambiar la temrinacion de dos lineas sin perder la rima]"
        "\n\nVerse 2:"
        "\n[8 líneas de la segunda estrofa]"
        "\n\nPre-Chorus:"
        "\n[4 líneas del pre-estribillo]"
        "\n\nChorus:"
        "\n[4 líneas del estribillo]"
        "\n\nChorus:"
        "\n[4 líneas del estribillo repetido]"
        "\n\nBridge:"
        "\n[4-8 líneas del puente, debe ser solo la letra]"
        "\n\nOutro:"
        "\n[4 líneas del final]"
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

    try:
        if llm_model.startswith("groq/"):
            # --- Lógica para Groq ---
            # El usuario ha especificado el modelo "openai/gpt-oss-120b".
            # Es importante notar que este nombre de modelo no es un modelo estándar
            # ofrecido directamente por la API de Groq y podría resultar en un error.
            # Se utilizará el nombre de modelo proporcionado por el usuario.
            #
            # El parámetro 'reasoning_effort' también ha sido omitido ya que no es
            # soportado por el cliente oficial de Groq.
            model_name = llm_model.split('/')[-1] # Extract "openai/gpt-oss-120b"
            print(f"Generando letras con Groq (Modelo: {model_name})...")
            
            completion = groq_client.chat.completions.create(
                model=model_name, # Using the user-specified model name
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=4096,
                top_p=1,
                stream=False,
            )
            return completion.choices[0].message.content

        else:
            # --- Lógica para OpenAI (Default) ---
            model_name = "gpt-4o-mini"
            print(f"Generando letras con OpenAI (Modelo: {model_name})...")
            response = openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content

    except Exception as e:
        print(f"Error al generar las letras para la canción {song_index} con el modelo {llm_model}: {e}")
        return "TITLE: Error\nPROMPT: [Letras no generadas por un error]\nTAGS: error"

def generate_instrumental_prompt_for_song(prompt: str, song_style: str, language: str = "spanish", song_index: int = 1, total_songs: int = 1) -> str:
    """
    Genera un prompt para una única canción instrumental (título y tags).
    NOTE: This still uses OpenAI by default as per user's request to only change lyric generation for now.
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

        response = openai_client.chat.completions.create(
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
