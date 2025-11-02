

import os
import openai
from src.config import OPENAI_API_KEY, METADATA_DIR

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def generate_youtube_metadata(lyrics: str, user_prompt: str, song_style: str) -> str:
    """
    Genera metadatos de YouTube usando OpenAI, los guarda en un archivo y devuelve la ruta.
    """
    print("Generando metadatos de YouTube con gpt-4o-mini...")
    try:
        system_prompt = (
            "Eres un experto en marketing de YouTube. Tu tarea es generar un título de video, una descripción y etiquetas relevantes basadas en la letra de una canción, el prompt original del usuario y el estilo musical. "
            "Debes devolver la información en un formato estructurado y fácil de parsear, exactamente como se especifica."
        )
        user_prompt_formatted = (
            f"Basado en el siguiente aviso del usuario: '{user_prompt}', el estilo musical: '{song_style}', y las letras de la canción:\n\n{lyrics}\n\n"
            "Genera lo siguiente para un video de YouTube:\n"
            "1. Un título de video pegadizo.\n"
            "2. Una descripción atractiva que resuma el ambiente y el estilo.\n"
            "3. Una lista de etiquetas relevantes separadas por comas, incluyendo el estilo musical.\n\n"
            "Formatea la salida exactamente así:\n"
            "Título: [Tu título aquí]\n"
            "Descripción: [Tu descripción aquí]\n"
            "Etiquetas: [etiqueta1, etiqueta2, etiqueta3]"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_formatted}
            ],
            temperature=0.7,
        )

        text_response = response.choices[0].message.content

    except Exception as e:
        print(f"Error al generar metadatos con OpenAI: {e}. Usando metadatos de respaldo.")
        # Create a fallback response string
        text_response = (
            f"Título: Canción sobre {user_prompt}\n"
            f"Descripción: Disfruta esta canción creada con IA sobre {user_prompt} en un estilo {song_style}.\n"
            f"Etiquetas: AI music, suno, music video, {user_prompt.replace(' ', '_')}, {song_style.replace(' ', '_')}"
        )

    # Ensure the metadata directory exists
    os.makedirs(METADATA_DIR, exist_ok=True)
    
    # Create a unique filename based on the user prompt
    safe_prompt = "".join(c for c in user_prompt if c.isalnum() or c in " _-").rstrip()
    metadata_filename = f"metadata_{safe_prompt[:20]}.txt"
    metadata_filepath = os.path.join(METADATA_DIR, metadata_filename)

    # Save the raw text response to the file
    with open(metadata_filepath, 'w', encoding='utf-8') as f:
        f.write(text_response)

    print(f"Metadatos guardados en: {metadata_filepath}")
    
    # Return the path to the file
    return metadata_filepath

