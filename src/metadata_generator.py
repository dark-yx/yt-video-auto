

import openai
from src.config import OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def generate_youtube_metadata(lyrics: str, user_prompt: str) -> dict:
    """
    Genera metadatos de YouTube a partir de las letras y el aviso inicial usando OpenAI.
    """
    print("Generando metadatos de YouTube con gpt-4o-mini...")
    try:
        system_prompt = (
            "Eres un experto en marketing de YouTube. Tu tarea es generar un título de video, una descripción y etiquetas relevantes basadas en la letra de una canción y el prompt original del usuario. "
            "Debes devolver la información en un formato estructurado y fácil de parsear, exactamente como se especifica."
        )
        user_prompt_formatted = (
            f"Basado en el siguiente aviso del usuario: '{user_prompt}' y las letras de la canción:\n\n{lyrics}\n\n"
            "Genera lo siguiente para un video de YouTube:\n"
            "1. Un título de video pegadizo.\n"
            "2. Una descripción atractiva y que resuma el ambiente.\n"
            "3. Una lista de etiquetas relevantes separadas por comas.\n\n"
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
        
        # Parse the response
        lines = text_response.strip().split('\n')
        title = lines[0].replace("Título:", "").strip()
        description = lines[1].replace("Descripción:", "").strip()
        tags_str = lines[2].replace("Etiquetas:", "").strip()
        tags = [tag.strip() for tag in tags_str.split(',')]

        return {"title": title, "description": description, "tags": tags}
    except Exception as e:
        print(f"Error al generar metadatos con OpenAI: {e}")
        return {
            "title": f"Canción sobre {user_prompt}",
            "description": "Disfruta esta canción creada con IA.",
            "tags": ["AI music", "suno", "music video"]
        }

