import openai
from groq import Groq
import google.generativeai as genai
from src.config import OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY
from src.utils import parse_lyrics_file
from typing import List, Dict

# Initialize clients for all services
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

def generate_draft_lyrics(
    prompt: str, 
    song_style: str, 
    language: str = "spanish", 
    gender: str = "Masculino", 
    song_index: int = 1, 
    total_songs: int = 1,
    llm_model: str = "openai/gpt-4o-mini"
) -> str:
    """
    Genera el borrador de la letra y tags para una única canción, usando el modelo de lenguaje especificado.
    """
    system_prompt_draft = (
        f"Eres un compositor. Tu tarea es escribir una canción completa y, por separado, detallar su estilo musical."
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
    user_prompt_draft = (
        f"Tema de la canción: '{prompt}'\n"
        f"Estilo musical general: '{song_style}'\n"
        f"Género del cantante: '{gender}'"
    )
    if total_songs > 1:
        user_prompt_draft += f"\nEsta es la canción {song_index} de un total de {total_songs}."

    try:
        if llm_model.startswith("groq/"):
            model_name = llm_model.split('/', 1)[1]
            print(f"Generando borrador de letras con Groq (Modelo: {model_name})...")
            completion = groq_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt_draft},
                    {"role": "user", "content": user_prompt_draft}
                ],
                temperature=0.7,
                max_tokens=4096,
                top_p=1,
                stream=False,
            )
            return completion.choices[0].message.content
        
        elif llm_model.startswith("gemini/"):
            model_name = llm_model.split('/', 1)[1]
            print(f"Generando borrador de letras con Google Gemini (Modelo: {model_name})...")
            model = genai.GenerativeModel(model_name)
            full_prompt = f"{system_prompt_draft}\n\n{user_prompt_draft}"
            response = model.generate_content(full_prompt)
            return response.text

        else: # Default to OpenAI
            model_name = llm_model.split('/', 1)[1]
            print(f"Generando borrador de letras con OpenAI (Modelo: {model_name})...")
            response = openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt_draft},
                    {"role": "user", "content": user_prompt_draft}
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content

    except Exception as e:
        print(f"Error al generar el borrador de las letras para la canción {song_index} con el modelo {llm_model}: {e}")
        return f"TITLE: Error Song {song_index}\nPROMPT: [Borrador no generado por un error: {e}]\nTAGS: error\nGENERO: "

def refine_lyrics(
    initial_user_prompt: str,
    draft_lyrics_content: str,
    song_style: str
) -> str:
    """
    Refina la letra de una canción usando un modelo de lenguaje avanzado (GPT-4o-mini).
    """
    print(f"Refinando letras para el prompt: '{initial_user_prompt}'...")
    
    try:
        parsed_draft = parse_lyrics_file(draft_lyrics_content)
        draft_lyrics = parsed_draft.get('prompt', '')
        if not draft_lyrics or "[Borrador no generado por un error" in draft_lyrics:
            print("Advertencia: No se pudo extraer una letra válida del borrador para refinar. Saltando refinamiento.")
            return draft_lyrics_content
    except Exception as e:
        print(f"Error al parsear el borrador de la letra: {e}. Saltando refinamiento.")
        return draft_lyrics_content

    system_prompt = (
        "Eres un compositor y letrista profesional de talla mundial, con un profundo conocimiento de la teoría musical, la poesía, la narrativa y la psicología de la música en todos los idiomas. "
        "Tu tarea es tomar un borrador de letra de canción y transformarlo en una obra maestra. "
        "Debes analizar el tema principal, el estilo musical y la letra del borrador, y luego reescribirla para maximizar su impacto, coherencia, "
        "calidad de rima, flujo y profundidad emocional. Utiliza todo tu conocimiento y entrenamiento sobre el tema para enriquecer la letra."
    )
    
    user_prompt = (
        f"Por favor, mejora la siguiente letra de canción para que alcance un nivel de autor profesional.\n"
        f"**Tema principal de la canción (Prompt Original):** '{initial_user_prompt}'\n"
        f"**Estilo Musical:** '{song_style}'\n\n"
        f"**Borrador de la Letra:**\n{draft_lyrics}\n\n"
        "**Instrucciones de Mejora Crítica:**\n"
        "1. **Coherencia y Narrativa Profunda:** Asegúrate de que la historia o el mensaje sea cristalino y se desarrolle con una tensión y liberación narrativa que cautive al oyente.\n"
        "2. **Calidad de Rima Excepcional:** Eleva las rimas. Busca rimas internas, asonantes, consonantes y multisilábicas que suenen naturales y sofisticadas. Las terminaciones de las palabras deben combinar y fluir perfectamente.\n"
        "3. **Flujo y Musicalidad:** Cada línea debe tener un ritmo y una cadencia que no solo se lea bien, sino que se sienta inherentemente musical. Piensa en cómo las sílabas y los acentos crearán un patrón rítmico sobre una melodía.\n"
        "4. **Profundidad y Originalidad:** Infunde la letra con metáforas originales, imágenes poéticas potentes y un lenguaje evocador que provoque una respuesta emocional genuina.\n"
        "5. **Sentido y Precisión:** Cada palabra debe estar ahí por una razón. La gramática debe ser impecable y cada frase debe ser concisa y poderosa.\n\n"
        "**IMPORTANTE:** Devuelve únicamente la letra mejorada, manteniendo la misma estructura de secciones (Intro, Verse 1, Chorus, etc.). No incluyas ningún texto adicional, explicaciones o comentarios."
    )

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        refined_lyrics = response.choices[0].message.content
        
        # Reconstruir el formato original con la letra refinada
        parsed_draft['prompt'] = refined_lyrics
        
        final_output = f"TITLE: {parsed_draft.get('title', 'Sin Título')}\n\n"
        final_output += f"PROMPT:\n{refined_lyrics}\n\n"
        final_output += f"TAGS:\n{parsed_draft.get('tags', '')}\n\n"
        final_output += f"GENERO: {parsed_draft.get('gender', '')}"
        
        return final_output

    except Exception as e:
        print(f"Error al refinar las letras con gpt-4o-mini: {e}")
        return draft_lyrics_content

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

def generate_song_plan(
    user_prompt: str,
    total_songs: int,
    language: str,
    llm_model: str = "openai/gpt-4o-mini"
) -> str:
    """
    Genera un plan de canciones con títulos y descripciones únicos.
    """
    print(f"Generando plan de canciones para el prompt: '{user_prompt}'...")

    system_prompt = (
        "Eres un productor musical y un conceptualizador creativo. Tu tarea es tomar una idea general para un álbum o una serie de canciones y desglosarla en una lista de temas de canciones únicos y originales. "
        "Cada tema debe tener un título y una breve descripción que sirva de guía para un compositor. "
        "El objetivo es evitar la repetición y asegurar que cada canción explore un ángulo, emoción o momento diferente dentro del concepto general."
    )

    user_prompt_plan = (
        f"Basado en el siguiente concepto general, genera un plan para {total_songs} canciones únicas.\n"
        f"**Concepto General:** '{user_prompt}'\n"
        f"**Idioma para los títulos y descripciones:** '{language}'\n\n"
        "**Instrucciones de Formato:**\n"
        "Devuelve tu respuesta como un único objeto JSON. La clave principal debe ser 'song_plan', y su valor debe ser un array de objetos.\n"
        "Cada objeto en el array debe tener exactamente dos claves: 'title' (un título de canción creativo y único) y 'description' (una descripción de 1-3 frases sobre el enfoque, la emoción o la historia de esa canción específica).\n"
        "Asegúrate de que no haya títulos duplicados y de que las descripciones guíen hacia letras distintas.\n\n"
        "**Ejemplo de Salida:**\n"
        "{\n"
        '  "song_plan": [\n'
        '    {\n'
        '      "title": "Ecos en la Lluvia",\n'
        '      "description": "La canción de apertura. Trata sobre el recuerdo melancólico de un amor pasado, evocado por el sonido de la lluvia en la ventana. El tono es nostálgico y un poco triste."\n'
        '    },\n'
        '    {\n'
        '      "title": "Calles de Neón",\n'
        '      "description": "Una canción más enérgica sobre la distracción y la soledad que se siente en una gran ciudad por la noche, intentando olvidar a esa persona. El ritmo es más rápido y la energía es de desesperación y búsqueda."\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        # Por ahora, esta función usará OpenAI por defecto para asegurar una salida JSON consistente.
        # Se puede extender en el futuro para otros modelos si se valida su capacidad de seguir instrucciones JSON.
        model_name = "gpt-4o-mini" # Forzar un modelo conocido para JSON
        print(f"Generando plan de canciones con OpenAI (Modelo: {model_name})...")
        
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_plan}
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"Error al generar el plan de canciones con el modelo {llm_model}: {e}")
        return '{"song_plan": []}'

