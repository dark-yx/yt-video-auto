
import os
import json
from typing import List, TypedDict, Dict
from langgraph.graph import StateGraph, END
from celery import Task

# Importar nuestros módulos de ayuda
from src.config import (
    LYRICS_DIR, SONGS_DIR, CLIPS_DIR, OUTPUT_DIR, 
    METADATA_DIR, PUBLICATION_REPORTS_DIR, VIDEO_OUTPUT_PATH
)
from src.lyric_generator import generate_lyrics_for_song, generate_instrumental_prompt_for_song
from src.suno_handler import create_and_download_song
from src.suno_api import SunoApiClient
from src.video_assembler import assemble_video
from src.metadata_generator import generate_youtube_metadata
from src.youtube_uploader import upload_video_to_youtube
from src.utils import parse_lyrics_file
import openai
from src.config import OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# --- Definir el estado del agente ---
class AgentState(TypedDict):
    user_prompt: str
    song_style: str
    num_female_songs: int
    num_male_songs: int
    language: str
    is_instrumental: bool
    with_subtitles: bool
    num_instrumental_songs: int
    lyrics_list: List[str]
    song_paths: List[str]
    metadata_path: str
    final_video_path: str
    youtube_url: str
    task_instance: Task
    suno_client: SunoApiClient
    resume_from_node: str

# --- Funciones de ayuda ---
def update_progress(task_instance: Task, step: int, total_steps: int, details: str):
    if not task_instance:
        print(f"(Simulado) Progreso: {details}")
        return
    progress_percentage = int((step / total_steps) * 100)
    task_instance.update_state(
        state='PROGRESS',
        meta={'details': details, 'progress': f'{progress_percentage}%'}
    )

TOTAL_STEPS = 6 # Ajustado a 6 pasos incluyendo la creación del informe

# --- Nodos del Grafo ---

def node_generate_lyrics(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 1, TOTAL_STEPS, "Iniciando generación de letras...")

    lyrics_list = []
    os.makedirs(LYRICS_DIR, exist_ok=True)

    is_instrumental = state.get("is_instrumental", False)
    num_female = state.get("num_female_songs", 0)
    num_male = state.get("num_male_songs", 0)

    if is_instrumental:
        total_songs = state.get("num_instrumental_songs", 1)
    else:
        total_songs = num_female + num_male

    for i in range(total_songs):
        song_index = i + 1
        update_progress(task, 1, TOTAL_STEPS, f"Generando texto para canción {song_index}/{total_songs}...")

        if is_instrumental:
            content = generate_instrumental_prompt_for_song(
                prompt=state["user_prompt"],
                song_style=state["song_style"],
                language=state.get("language", "spanish"),
                song_index=song_index,
                total_songs=total_songs
            )
        else:
            # Determinar el género para la canción actual
            gender = "Femenino" if i < num_female else "Masculino"
            
            content = generate_lyrics_for_song(
                prompt=state["user_prompt"],
                song_style=state["song_style"],
                language=state.get("language", "spanish"),
                gender=gender,
                song_index=song_index,
                total_songs=total_songs
            )
        
        lyrics_list.append(content)

        # Guardar el archivo .txt inmediatamente
        try:
            parsed_data = parse_lyrics_file(content)
            title = parsed_data.get('title', f'song_{song_index}')
            safe_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
            # Añadir el song_index al nombre del archivo para organización y evitar sobrescrituras
            filepath = os.path.join(LYRICS_DIR, f"{song_index}_{safe_title}.txt")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Texto de canción guardado en: {filepath}")
        except Exception as e:
            print(f"Error al guardar el archivo de letras para la canción {song_index}: {e}")

    return {"lyrics_list": lyrics_list}

def node_create_songs(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 2, TOTAL_STEPS, "Creando canciones con Suno...")

    lyrics_list = state["lyrics_list"]
    song_paths = []
    final_lyrics_for_video = [] # Use a new list for lyrics that successfully become songs

    for i, lyrics_file_content in enumerate(lyrics_list):
        # Use the new robust parser
        parsed_data = parse_lyrics_file(lyrics_file_content)
        
        # The 'song_style' from the initial state can be a fallback if tags are not in the file
        tags = parsed_data['tags'] if parsed_data['tags'] else state["song_style"]
        
        update_progress(task, 2, TOTAL_STEPS, f"Generando canción {i+1}/{len(lyrics_list)} ('{parsed_data['title']}') con voz {parsed_data['gender']}...")

        # Create and download the song(s) using the parsed data
        new_song_paths = create_and_download_song(
            client=state["suno_client"],
            lyrics=parsed_data['prompt'],
            song_style=tags,
            song_title=parsed_data['title'],
            vocal_gender=parsed_data['gender'],
            is_instrumental=state.get("is_instrumental", False),
            task_instance=task
        )
        
        if new_song_paths:
            song_paths.extend(new_song_paths)
            # Only add the lyrics to the final list if a song was successfully created
            final_lyrics_for_video.append(parsed_data['prompt'])

    if not song_paths:
        raise ValueError("No se pudo generar ninguna canción.")

    # Return the paths of the created songs and the corresponding lyrics for the video assembler
    return {"song_paths": song_paths, "lyrics_list": final_lyrics_for_video}

def node_assemble_video(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 3, TOTAL_STEPS, "Ensamblando el video...")

    final_path = assemble_video(
        song_paths=state["song_paths"],
        lyrics_list=state["lyrics_list"],
        with_subtitles=state.get("with_subtitles", True)
    )
    
    return {"final_video_path": final_path}

def node_generate_metadata(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 4, TOTAL_STEPS, "Generando metadatos para YouTube...")

    # Usar la primera letra como base para los metadatos
    base_lyrics = state["lyrics_list"][0] if state["lyrics_list"] else ""

    metadata_path = generate_youtube_metadata(
        user_prompt=state["user_prompt"],
        song_style=state["song_style"],
        lyrics=base_lyrics
    )
    
    return {"metadata_path": metadata_path}

def node_upload_to_youtube(state: AgentState) -> Dict:

    task = state["task_instance"]

    update_progress(task, 5, TOTAL_STEPS, "Subiendo a YouTube...")



    # Leer los metadatos desde el archivo

    with open(state["metadata_path"], 'r', encoding='utf-8') as f:

        lines = f.readlines()

        title = lines[0].replace("Title:", "").strip()

        description = lines[1].replace("Description:", "").strip()

        tags_str = lines[2].replace("Tags:", "").strip()

        tags = [tag.strip() for tag in tags_str.split(',')]



    video_url = upload_video_to_youtube(

        video_path=state["final_video_path"],

        title=title,

        description=description,

        tags=tags,

        task_instance=task,

        privacy_status="private"

    )

    return {"youtube_url": video_url}

def node_create_publication_report(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 6, TOTAL_STEPS, "Creando informe de publicación...")
    
    os.makedirs(PUBLICATION_REPORTS_DIR, exist_ok=True)
    report_filename = f"report_{os.path.splitext(os.path.basename(state['final_video_path']))[0]}.txt"
    report_filepath = os.path.join(PUBLICATION_REPORTS_DIR, report_filename)

    report_content = {
        "user_prompt": state.get("user_prompt"),
        "song_style": state.get("song_style"),
        "youtube_url": state.get("youtube_url"),
        "final_video_path": state.get("final_video_path"),
        "metadata_path": state.get("metadata_path"),
        "song_paths": state.get("song_paths"),
    }

    with open(report_filepath, 'w', encoding='utf-8') as f:
        json.dump(report_content, f, indent=4)

    print(f"Informe de publicación guardado en: {report_filepath}")
    return {}

def node_create_publication_report(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 6, TOTAL_STEPS, "Creando informe de publicación...")
    
    os.makedirs(PUBLICATION_REPORTS_DIR, exist_ok=True)
    report_filename = f"report_{os.path.splitext(os.path.basename(state['final_video_path']))[0]}.json"
    report_filepath = os.path.join(PUBLICATION_REPORTS_DIR, report_filename)

    # Re-leer los metadatos del archivo para el informe
    with open(state["metadata_path"], 'r', encoding='utf-8') as f:
        lines = f.readlines()
        title = lines[0].replace("Title:", "").strip()
        description = lines[1].replace("Description:", "").strip()
        tags_str = lines[2].replace("Tags:", "").strip()
        tags = [tag.strip() for tag in tags_str.split(',')]
        video_metadata = {"title": title, "description": description, "tags": tags}

    report_content = {
        "user_prompt": state.get("user_prompt"),
        "song_style": state.get("song_style"),
        "youtube_url": state.get("youtube_url"),
        "final_video_path": state.get("final_video_path"),
        "video_metadata": video_metadata,
        "song_paths": state.get("song_paths"),
    }

    with open(report_filepath, 'w', encoding='utf-8') as f:
        json.dump(report_content, f, indent=4, ensure_ascii=False)

    print(f"Informe de publicación guardado en: {report_filepath}")
    return {}

# --- Lógica de Enrutamiento y Grafo ---

def route_workflow(state: AgentState) -> str:
    if state.get("resume_from_node"):
        print(f"Reanudando flujo de trabajo desde el nodo: {state['resume_from_node']}")
        return state["resume_from_node"]
    print("Iniciando nuevo flujo de trabajo desde 'generate_lyrics'")
    return "generate_lyrics"

workflow = StateGraph(AgentState)
workflow.add_node("generate_lyrics", node_generate_lyrics)
workflow.add_node("create_songs", node_create_songs)
workflow.add_node("assemble_video", node_assemble_video)
workflow.add_node("generate_metadata", node_generate_metadata)
workflow.add_node("upload_to_youtube", node_upload_to_youtube)
workflow.add_node("create_publication_report", node_create_publication_report)

workflow.set_conditional_entry_point(route_workflow)

workflow.add_edge("generate_lyrics", "create_songs")
workflow.add_edge("create_songs", "assemble_video")
workflow.add_edge("assemble_video", "generate_metadata")
workflow.add_edge("generate_metadata", "upload_to_youtube")
workflow.add_edge("upload_to_youtube", "create_publication_report")
workflow.add_edge("create_publication_report", END)

app_graph = workflow.compile()

# --- Puntos de Entrada del Flujo de Trabajo ---

def run_video_workflow(initial_state: dict):
    print("Iniciando el flujo de trabajo de generación de video de IA...")
    final_state = app_graph.invoke(initial_state)
    print("--- Flujo de trabajo completado ---")
    return {
        "youtube_url": final_state.get("youtube_url"),
        "video_path": final_state.get("final_video_path"),
        "song_paths": final_state.get("song_paths"),
    }

def resume_video_workflow(initial_state: dict):
    print("Iniciando el flujo de trabajo de reanudación de video...")
    
    def get_files_by_ext(directory, extensions):
        if not os.path.exists(directory): return []
        return [os.path.join(directory, f) for f in os.listdir(directory) if not f.startswith('.') and any(f.endswith(ext) for ext in extensions)]

    # 1. Inspeccionar el estado del sistema de archivos
    report_files = get_files_by_ext(PUBLICATION_REPORTS_DIR, ['.json'])
    if report_files:
        raise ValueError("Proceso ya completado. Se encontró un informe de publicación.")

    lyrics_files = get_files_by_ext(LYRICS_DIR, ['.txt'])
    song_files = get_files_by_ext(SONGS_DIR, ['.mp3'])
    clip_files = get_files_by_ext(CLIPS_DIR, ['.mp4', '.mov'])
    metadata_files = get_files_by_ext(METADATA_DIR, ['.json'])
    final_video_exists = os.path.exists(VIDEO_OUTPUT_PATH)

    # 2. Construir el estado inicial
    state = AgentState(**initial_state)
    state['lyrics_list'] = [open(f, 'r', encoding='utf-8').read() for f in sorted(lyrics_files)]
    state['song_paths'] = sorted(song_files)
    state['final_video_path'] = VIDEO_OUTPUT_PATH if final_video_exists else None
    state['user_prompt'] = "Sesión Reanudada"
    state['song_style'] = "Estilo Reanudado"
    
    if metadata_files:
        state['metadata_path'] = metadata_files[0]
    else:
        state['metadata_path'] = None

    # 3. Determinar el punto de reanudación
    if final_video_exists and state['metadata_path']:
        state['resume_from_node'] = "upload_to_youtube"
    elif final_video_exists:
        state['resume_from_node'] = "generate_metadata"
    elif lyrics_files and song_files:
        if not clip_files:
            raise ValueError("Faltan clips de video. Por favor, añade archivos .mp4 o .mov a la carpeta 'clips' para continuar.")
        state['resume_from_node'] = "assemble_video"
    elif lyrics_files:
        state['resume_from_node'] = "create_songs"
    else:
        raise ValueError("No hay suficiente progreso para reanudar. Inicia un nuevo proceso.")

    # 4. Invocar el grafo
    final_state = app_graph.invoke(state)
    print("--- Flujo de trabajo de reanudación completado ---")
    
    return {
        "youtube_url": final_state.get("youtube_url"),
        "video_path": final_state.get("final_video_path"),
    }
