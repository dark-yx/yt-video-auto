
import google.generativeai as genai
from src.config import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)

def generate_youtube_metadata(lyrics: str, user_prompt: str) -> dict:
    """
    Genera metadatos de YouTube a partir de las letras y el aviso inicial.
    """
    print("Generando metadatos de YouTube...")
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = (
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
        response = model.generate_content(prompt)
        
        # Parse the response
        lines = response.text.strip().split('\n')
        title = lines[0].replace("Título:", "").strip()
        description = lines[1].replace("Descripción:", "").strip()
        tags_str = lines[2].replace("Etiquetas:", "").strip()
        tags = [tag.strip() for tag in tags_str.split(',')]

        return {"title": title, "description": description, "tags": tags}
    except Exception as e:
        print(f"Error al generar metadatos: {e}")
        return {
            "title": f"Canción sobre {user_prompt}",
            "description": "Disfruta esta canción creada con IA.",
            "tags": ["AI music", "suno", "music video"]
        }
