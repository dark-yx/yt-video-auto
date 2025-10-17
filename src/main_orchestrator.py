
from typing import List, TypedDict, Annotated, Dict
from langgraph.graph import StateGraph, END
import operator

# Importar nuestros módulos de ayuda
from src.config import VIDEO_OUTPUT_PATH
from src.lyric_generator import generate_lyrics
from src.suno_handler import create_and_download_song
from src.video_assembler import assemble_video
from src.metadata_generator import generate_youtube_metadata
from src.youtube_uploader import upload_video_to_youtube

# --- Definir el estado del agente ---
class AgentState(TypedDict):
    initial_prompt: str
    song_style: str
    num_songs: int
    lyrics_list: List[str]
    song_paths: List[str]
    video_metadata: Dict[str, str]
    final_video_path: str

# --- Definir los nodos del gráfico ---

def node_generate_lyrics(state: AgentState) -> AgentState:
    """Genera una lista de letras basadas en el aviso inicial."""
    print("--- Nodo: Generando letras ---")
    lyrics_list = []
    for i in range(state["num_songs"]):
        prompt = f"{state['initial_prompt']} (Parte {i+1}/{state['num_songs']})"
        lyrics = generate_lyrics(prompt, state["song_style"])
        if lyrics:
            lyrics_list.append(lyrics)
    return {"lyrics_list": lyrics_list}

def node_create_songs(state: AgentState) -> AgentState:
    """Utiliza las letras para generar archivos de canciones con Suno."""
    print("--- Nodo: Creando canciones con Suno ---")
    song_paths = []
    for i, lyrics in enumerate(state["lyrics_list"]):
        title = f"Cancion_IA_{i+1}"
        song_path = create_and_download_song(lyrics, state["song_style"], title)
        if song_path:
            song_paths.append(song_path)
    return {"song_paths": song_paths}

def node_assemble_video(state: AgentState) -> AgentState:
    """Ensambla el video final a partir de clips, audio y letras."""
    print("--- Nodo: Ensamblando video ---")
    final_path = assemble_video(
        state["song_paths"],
        state["lyrics_list"],
        state["num_songs"]
    )
    return {"final_video_path": final_path}

def node_generate_metadata(state: AgentState) -> AgentState:
    """Genera metadatos de YouTube a partir de las letras combinadas."""
    print("--- Nodo: Generando metadatos de YouTube ---")
    full_lyrics = "\n\n---\n\n".join(state["lyrics_list"])
    metadata = generate_youtube_metadata(full_lyrics)
    return {"video_metadata": metadata}

def node_upload_to_youtube(state: AgentState):
    """Carga el video final en YouTube."""
    print("--- Nodo: Cargando a YouTube ---")
    if not state["final_video_path"] or not os.path.exists(state["final_video_path"]):
        print("Error: No se encontró la ruta del video final. Abortando la carga.")
        return
    
    metadata = state["video_metadata"]
    upload_video_to_youtube(
        video_path=state["final_video_path"],
        title=metadata.get("title", "Video de IA"),
        description=metadata.get("description", "Creado con IA."),
        tags=metadata.get("tags", "ia,música,generativo")
    )
    print("--- ¡Flujo de trabajo completado! ---")

# --- Construir y ejecutar el gráfico ---

workflow = StateGraph(AgentState)

# Añadir nodos al gráfico
workflow.add_node("generar_letras", node_generate_lyrics)
workflow.add_node("crear_canciones", node_create_songs)
workflow.add_node("ensamblar_video", node_assemble_video)
workflow.add_node("generar_metadatos", node_generate_metadata)
workflow.add_node("cargar_a_youtube", node_upload_to_youtube)

# Definir las transiciones (el flujo de trabajo)
workflow.set_entry_point("generar_letras")
workflow.add_edge("generar_letras", "crear_canciones")
workflow.add_edge("crear_canciones", "ensamblar_video")
workflow.add_edge("ensamblar_video", "generar_metadatos")
workflow.add_edge("generar_metadatos", "cargar_a_youtube")
workflow.add_edge("cargar_a_youtube", END)

# Compilar el gráfico
app = workflow.compile()

# --- Punto de entrada principal para ejecutar el flujo de trabajo ---
if __name__ == "__main__":
    # 1. Agregue sus videoclips de origen a la carpeta `src/clips`.
    # 2. Configure su archivo `.env` y `client_secrets.json`.
    # 3. Defina su aviso y estilo iniciales a continuación.

    initial_state = {
        "initial_prompt": "Una canción sobre una aventura espacial a un planeta lejano",
        "song_style": "Pop electrónico, optimista, synthwave",
        "num_songs": 2 # Establecer en 24 para un video de una hora
    }

    print("Iniciando el flujo de trabajo de generación de video de IA...")
    # Ejecutar el flujo de trabajo
    app.invoke(initial_state)
