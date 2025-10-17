
import google.generativeai as genai
from src.config import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)


def generate_lyrics(prompt: str, song_style: str) -> str:
    """
    Genera letras de canciones utilizando la API de Gemini según un aviso y un estilo.
    """
    print(f"Generando letras con el estilo: {song_style}")
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(
            f"Escribe una canción completa con el siguiente tema: '{prompt}'. "
            f"La canción debe tener un estilo de '{song_style}'. "
            f"Incluye secciones como [Estrofa], [Estribillo] y [Puente]."
        )
        return response.text
    except Exception as e:
        print(f"Error al generar las letras: {e}")
        return ""
