
import os
from typing import List, TypedDict, Dict
from langgraph.graph import StateGraph, END
from celery import Task

# Importar nuestros módulos de ayuda
from src.config import VIDEO_OUTPUT_PATH
from src.lyric_generator import generate_lyrics
from src.suno_handler import create_and_download_song
from src.video_assembler import assemble_video
from src.metadata_generator import generate_youtube_metadata
from src.youtube_uploader import upload_video_to_youtube

# --- Definir el estado del agente ---
class AgentState(TypedDict):
    user_prompt: str
    song_style: str
    num_songs: int
    lyrics_list: List[str]
    song_paths: List[str]
    video_metadata: Dict[str, str]
    final_video_path: str
    youtube_url: str
    task_instance: Task # La instancia de la tarea de Celery para reportar progreso

# --- Funciones de ayuda para actualizar el estado ---
def update_progress(task_instance: Task, step: int, total_steps: int, details: str):
    """Función centralizada para enviar actualizaciones de progreso a Celery."""
    if not task_instance:
        print(f"(Simulado) Progreso: {details}")
        return
    
    progress_percentage = int((step / total_steps) * 100)
    task_instance.update_state(
        state='PROGRESS',
        meta={'details': details, 'progress': f'{progress_percentage}%'}
    )

# --- Definir los nodos del gráfico ---
TOTAL_STEPS = 5 # Número total de pasos principales

def node_generate_lyrics(state: AgentState) -> Dict[str, List[str]]:
    task = state["task_instance"]
    update_progress(task, 1, TOTAL_STEPS, f"Generando {state['num_songs']} conjunto(s) de letras...")
    
    lyrics_list = generate_lyrics(state["user_prompt"], state["song_style"], state["num_songs"])
    return {"lyrics_list": lyrics_list}

def node_create_songs(state: AgentState) -> Dict[str, List[str]]:
    task = state["task_instance"]
    update_progress(task, 2, TOTAL_STEPS, "Componiendo canciones con Suno AI...")

    song_paths = []
    for i, lyrics in enumerate(state["lyrics_list"]):
        title = f"Generated_Song_{i+1}"
        song_path = create_and_download_song(lyrics, state["song_style"], title, task)
        if song_path:
            song_paths.append(song_path)
    return {"song_paths": song_paths}

def node_assemble_video(state: AgentState) -> Dict[str, str]:
    task = state["task_instance"]
    update_progress(task, 3, TOTAL_STEPS, "Ensamblando el video...")
    
    final_path = assemble_video(state["song_paths"], state["lyrics_list"], task)
    return {"final_video_path": final_path}

def node_generate_metadata(state: AgentState) -> Dict[str, Dict[str, str]]:
    task = state["task_instance"]
    update_progress(task, 4, TOTAL_STEPS, "Generando metadatos de YouTube...")
    
    full_lyrics = "\n\n---\n\n".join(state["lyrics_list"])
    metadata = generate_youtube_metadata(full_lyrics, state["user_prompt"])
    return {"video_metadata": metadata}

def node_upload_to_youtube(state: AgentState) -> Dict[str, str]:
    task = state["task_instance"]
    update_progress(task, 5, TOTAL_STEPS, "Subiendo a YouTube...")

    video_url = upload_video_to_youtube(
        video_path=state["final_video_path"],
        title=state["video_metadata"]["title"],
        description=state["video_metadata"]["description"],
        tags=state["video_metadata"]["tags"],
        task_instance=task
    )
    return {"youtube_url": video_url}

# --- Construir el gráfico ---
workflow = StateGraph(AgentState)
workflow.add_node("generate_lyrics", node_generate_lyrics)
workflow.add_node("create_songs", node_create_songs)
workflow.add_node("assemble_video", node_assemble_video)
workflow.add_node("generate_metadata", node_generate_metadata)
workflow.add_node("upload_to_youtube", node_upload_to_youtube)

workflow.set_entry_point("generate_lyrics")
workflow.add_edge("generate_lyrics", "create_songs")
workflow.add_edge("create_songs", "assemble_video")
workflow.add_edge("assemble_video", "generate_metadata")
workflow.add_edge("generate_metadata", "upload_to_youtube")
workflow.add_edge("upload_to_youtube", END)

app_graph = workflow.compile()

# --- Punto de entrada principal ---
def run_video_workflow(initial_state: dict):
    print("Iniciando el flujo de trabajo de generación de video de IA...")
    final_state = app_graph.invoke(initial_state)
    print("--- Flujo de trabajo completado ---")
    
    # Limpiamos y devolvemos los resultados clave
    return {
        "title": final_state.get("video_metadata", {}).get("title"),
        "description": final_state.get("video_metadata", {}).get("description"),
        "youtube_url": final_state.get("youtube_url"),
        "video_path": final_state.get("final_video_path"),
        "song_paths": final_state.get("song_paths"),
    }
