
import google.generativeai as genai
from src.config import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)

def generate_youtube_metadata(lyrics: str) -> dict:
    """
    Genera el título, la descripción y las etiquetas de YouTube a partir de las letras de las canciones.
    """
    print("Generando metadatos de YouTube...")
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = (
            "Basado en las siguientes letras de canciones, genera un título de video de YouTube, "
            "una descripción y una lista de etiquetas separadas por comas. El título debe ser pegadizo y "
            "relevante. La descripción debe ser atractiva y resumir el estado de ánimo de la canción. "
            "Las etiquetas deben ser palabras clave relevantes.\n\n" + lyrics
        )
        response = model.generate_content(prompt)

        # Analizar la respuesta para extraer título, descripción y etiquetas
        parts = response.text.split('\n')
        title = parts[0].replace("Título:", "").strip()
        description = parts[1].replace("Descripción:", "").strip()
        tags = parts[2].replace("Etiquetas:", "").strip()

        return {"title": title, "description": description, "tags": tags}
    except Exception as e:
        print(f"Error al generar metadatos: {e}")
        return {
            "title": "Mi nueva canción (título predeterminado)",
            "description": "Disfruta de esta nueva canción generada por IA.",
            "tags": "música de ia,suno,video musical"
        }
