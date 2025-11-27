
import os
import json
import re
from typing import List, TypedDict, Dict
from langgraph.graph import StateGraph, END
from celery import Task

# Importar nuestros módulos de ayuda
from src.config import (
    LYRICS_DIR, SONGS_DIR, CLIPS_DIR, OUTPUT_DIR, 
    METADATA_DIR, PUBLICATION_REPORTS_DIR, VIDEO_OUTPUT_PATH
)
from src.lyric_generator import (
    generate_draft_lyrics, 
    refine_lyrics, 
    generate_instrumental_prompt_for_song,
    generate_song_plan
)
from src.suno_handler import create_and_download_song
from src.suno_api import SunoApiClient
from src.video_assembler import assemble_video
from src.metadata_generator import generate_youtube_metadata
from src.youtube_uploader import upload_video_to_youtube
from src.utils import parse_lyrics_file

# --- Funciones de ayuda de ordenación ---
def natural_sort_key(s):
    """
    Clave de ordenación natural para cadenas que contienen números.
    Maneja correctamente casos como: 1_cancion_a.mp3, 1_cancion_b.mp3, 2_cancion_a.mp3
    """
    def atoi(text):
        return int(text) if text.isdigit() else text.lower()
    
    return [atoi(c) for c in re.split(r'(\d+)', s)]

# --- Definir el estado del agente ---
class AgentState(TypedDict):
    user_prompt: str
    song_style: str
    num_female_songs: int
    num_male_songs: int
    language: str
    is_instrumental: bool
    with_subtitles: bool
    refine_lyrics: bool # NUEVO: Flag para controlar el refinamiento
    num_instrumental_songs: int
    llm_model: str
    suno_model: str
    song_plan: List[Dict] # NUEVO: Plan de canciones
    draft_filepaths: List[str]
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

TOTAL_STEPS = 8 # Ajustado a 8 pasos (plan, borrador, etc.)

# --- Lógica de enrutamiento condicional ---
def should_refine_lyrics(state: AgentState) -> str:
    """
    Determina si se debe pasar al nodo de refinamiento o saltar directamente a la creación de canciones.
    """
    if state.get("is_instrumental"):
        print("➡️ Decisión: Es instrumental, saltando refinamiento.")
        return "create_songs"
    if state.get("refine_lyrics", True): # Por defecto, refinar si no se especifica
        print("➡️ Decisión: Proceder al refinamiento de letras.")
        return "refine_lyrics"
    else:
        print("➡️ Decisión: Saltar el refinamiento de letras.")
        return "create_songs"

# --- Nodos del Grafo ---

def node_generate_song_plan(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 1, TOTAL_STEPS, "Fase 1: Creando plan de canciones...")

    is_instrumental = state.get("is_instrumental", False)
    if is_instrumental:
        total_songs = state.get("num_instrumental_songs", 1)
    else:
        total_songs = state.get("num_female_songs", 0) + state.get("num_male_songs", 0)

    if total_songs == 0:
        raise ValueError("El número total de canciones no puede ser cero.")

    # Para canciones instrumentales, no necesitamos un plan de letras detallado.
    if is_instrumental:
        song_plan = [{"title": f"Instrumental Song {i+1}", "description": state["user_prompt"]} for i in range(total_songs)]
        return {"song_plan": song_plan}

    plan_str = generate_song_plan(
        user_prompt=state["user_prompt"],
        total_songs=total_songs,
        language=state.get("language", "spanish"),
        llm_model=state.get("llm_model", "openai/gpt-4o-mini")
    )
    
    try:
        plan_data = json.loads(plan_str)
        song_plan = plan_data.get("song_plan", [])
        if not song_plan or len(song_plan) != total_songs:
            print(f"⚠️ Advertencia: El plan de canciones no se generó correctamente. Se generarán {total_songs} canciones sin un plan detallado.")
            song_plan = [{"title": f"Song {i+1}", "description": state["user_prompt"]} for i in range(total_songs)]
    except json.JSONDecodeError:
        print("Error al decodificar el JSON del plan de canciones. Se generarán canciones sin un plan detallado.")
        song_plan = [{"title": f"Song {i+1}", "description": state["user_prompt"]} for i in range(total_songs)]

    # Guardar el plan en un archivo para que sea visible
    os.makedirs(METADATA_DIR, exist_ok=True)
    plan_filepath = os.path.join(METADATA_DIR, "song_plan.json")
    with open(plan_filepath, 'w', encoding='utf-8') as f:
        json.dump(song_plan, f, indent=4, ensure_ascii=False)
    print(f"Plan de canciones guardado en: {plan_filepath}")

    return {"song_plan": song_plan}


def node_generate_lyrics_drafts(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 2, TOTAL_STEPS, "Fase 2: Creando borradores de letras...")

    song_plan = state.get("song_plan")
    if not song_plan:
        print("Plan de canciones no encontrado en el estado, intentando cargar desde archivo...")
        plan_filepath = os.path.join(METADATA_DIR, "song_plan.json")
        if os.path.exists(plan_filepath):
            with open(plan_filepath, 'r', encoding='utf-8') as f:
                song_plan = json.load(f)
            print("Plan de canciones cargado exitosamente desde el archivo.")
        else:
            raise ValueError("No se encontró el plan de canciones ni en el estado ni en el archivo. No se puede continuar.")

    draft_filepaths = []
    os.makedirs(LYRICS_DIR, exist_ok=True)
    generated_titles = set()
    
    total_songs = len(song_plan)
    num_female = state.get("num_female_songs", 0)

    for i, song_idea in enumerate(song_plan):
        song_index = i + 1
        update_progress(task, 2, TOTAL_STEPS, f"Generando borrador {song_index}/{total_songs}: '{song_idea.get('title')}'...")

        # Determinar el género para esta canción específica
        gender = "Femenino" if i < num_female else "Masculino"
        
        # Crear un prompt más detallado para el compositor de letras
        detailed_prompt = (
            f"Título de la canción: \"{song_idea.get('title')}\".\n"
            f"Descripción del tema: \"{song_idea.get('description')}\".\n"
            f"Basado en el concepto general: \"{state['user_prompt']}\"."
        )

        # Para instrumentales, el plan es más simple, solo generamos el prompt de Suno
        if state.get("is_instrumental", False):
            content = generate_instrumental_prompt_for_song(
                prompt=detailed_prompt,
                song_style=state["song_style"],
                language=state.get("language", "spanish"),
                song_index=song_index,
                total_songs=total_songs
            )
            # Forzar el título del plan en el contenido
            content = f"TITLE: {song_idea.get('title')}\n{content.split('TAGS:', 1)[-1]}"
        else:
            content = generate_draft_lyrics(
                prompt=detailed_prompt,
                song_style=state["song_style"],
                language=state.get("language", "spanish"),
                gender=gender,
                song_index=song_index,
                total_songs=total_songs,
                llm_model=state.get("llm_model", "openai/gpt-4o-mini")
            )
        
        try:
            # Asegurarse de que el título del plan se use, evitando el que genera el LLM
            parsed_data = parse_lyrics_file(content)
            original_title = song_idea.get('title', f'song_{song_index}')
            
            # Reemplazar el título en el contenido por el del plan para consistencia
            if parsed_data.get('title') != original_title:
                print(f"Forzando título del plan: '{original_title}' sobre el título generado '{parsed_data.get('title')}'.")
                content = content.replace(f"TITLE: {parsed_data.get('title')}", f"TITLE: {original_title}", 1)

            new_title = original_title
            suffix_n = 2
            while new_title in generated_titles:
                new_title = f"{original_title} ({suffix_n})"
                suffix_n += 1

            if new_title != original_title:
                print(f"⚠️ Título duplicado detectado en el plan. Renombrando '{original_title}' a '{new_title}'.")
                content = content.replace(f"TITLE: {original_title}", f"TITLE: {new_title}", 1)
            
            generated_titles.add(new_title)
            
            safe_title = "".join(c for c in new_title if c.isalnum() or c in " _-").rstrip()
            filepath = os.path.join(LYRICS_DIR, f"{song_index}_{safe_title}.txt")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Borrador de canción guardado en: {filepath}")
            draft_filepaths.append(filepath)

        except Exception as e:
            print(f"Error al procesar y guardar el borrador para la canción {song_index}: {e}")

    return {"draft_filepaths": draft_filepaths}

def node_refine_lyrics(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 2, TOTAL_STEPS, "Fase 2: Refinando letras con modelo avanzado...")
    
    refined_lyrics_list = []
    draft_filepaths = state["draft_filepaths"]

    for i, filepath in enumerate(draft_filepaths):
        update_progress(task, 2, TOTAL_STEPS, f"Refinando letra {i+1}/{len(draft_filepaths)}...")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                draft_content = f.read()

            refined_content = refine_lyrics(
                initial_user_prompt=state["user_prompt"],
                draft_lyrics_content=draft_content,
                song_style=state["song_style"]
            )
            
            # Sobrescribir el archivo con el contenido refinado
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(refined_content)
            
            print(f"Letra refinada y guardada en: {filepath}")
            refined_lyrics_list.append(refined_content)
        except Exception as e:
            print(f"Error al refinar el archivo {filepath}: {e}")
            # Si falla el refinamiento, añadir el contenido original a la lista
            if 'draft_content' in locals():
                refined_lyrics_list.append(draft_content)

    return {"lyrics_list": refined_lyrics_list}

def node_create_songs(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 3, TOTAL_STEPS, "Fase 3: Creando canciones con Suno...")

    # Si se saltó el refinamiento, las letras no estarán en el estado. Las leemos de los archivos.
    lyrics_list = state.get("lyrics_list")
    if not lyrics_list:
        print("No se encontraron letras refinadas en el estado, leyendo desde los archivos de borrador.")
        lyrics_list = []
        draft_filepaths = state.get("draft_filepaths", [])
        for filepath in draft_filepaths:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lyrics_list.append(f.read())
            except Exception as e:
                print(f"⚠️ Error al leer el archivo de borrador {filepath}: {e}")

    song_paths = []
    final_lyrics_for_video = []

    for i, lyrics_file_content in enumerate(lyrics_list):
        parsed_data = parse_lyrics_file(lyrics_file_content)
        tags = parsed_data.get('tags') or state["song_style"]
        
        update_progress(task, 3, TOTAL_STEPS, f"Generando canción {i+1}/{len(lyrics_list)} ('{parsed_data.get('title', 'N/A')}') con voz {parsed_data.get('gender', 'N/A')}...")

        new_song_paths = create_and_download_song(
            client=state["suno_client"],
            lyrics=parsed_data.get('prompt', ''),
            song_style=tags,
            song_title=parsed_data.get('title', f'song_{i+1}'),
            vocal_gender=parsed_data.get('gender'),
            is_instrumental=state.get("is_instrumental", False),
            task_instance=task,
            suno_model=state.get("suno_model", "chirp-crow")
        )
        
        if new_song_paths:
            song_paths.extend(new_song_paths)
            # Añadir la letra correspondiente por cada canción generada para mantener la sincronización
            final_lyrics_for_video.extend([parsed_data.get('prompt', '')] * len(new_song_paths))

    if not song_paths:
        raise ValueError("No se pudo generar ninguna canción.")

    song_paths = sorted(song_paths, key=natural_sort_key)
    
    print("\n=== ORDEN FINAL DE CANCIONES ===")
    for idx, path in enumerate(song_paths, 1):
        print(f"{idx}. {os.path.basename(path)}")
    print("================================\n")

    return {"song_paths": song_paths, "lyrics_list": final_lyrics_for_video}

def node_assemble_video(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 4, TOTAL_STEPS, "Fase 4: Ensamblando el video...")

    final_path = assemble_video(
        song_paths=state["song_paths"],
        lyrics_list=state["lyrics_list"],
        with_subtitles=state.get("with_subtitles", True)
    )
    
    return {"final_video_path": final_path}

def node_generate_metadata(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 5, TOTAL_STEPS, "Fase 5: Generando metadatos para YouTube...")

    base_lyrics = state["lyrics_list"][0] if state["lyrics_list"] else ""

    metadata_path = generate_youtube_metadata(
        user_prompt=state["user_prompt"],
        song_style=state["song_style"],
        lyrics=base_lyrics
    )
    
    return {"metadata_path": metadata_path}

def node_upload_to_youtube(state: AgentState) -> Dict:
    task = state["task_instance"]
    update_progress(task, 6, TOTAL_STEPS, "Fase 6: Subiendo a YouTube...")

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
    update_progress(task, 7, TOTAL_STEPS, "Fase 7: Creando informe de publicación...")
    
    os.makedirs(PUBLICATION_REPORTS_DIR, exist_ok=True)
    report_filename = f"report_{os.path.splitext(os.path.basename(state['final_video_path']))[0]}.json"
    report_filepath = os.path.join(PUBLICATION_REPORTS_DIR, report_filename)

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
    print("Iniciando nuevo flujo de trabajo desde 'generate_song_plan'")
    return "generate_song_plan"

workflow = StateGraph(AgentState)
workflow.add_node("generate_song_plan", node_generate_song_plan)
workflow.add_node("generate_lyrics_drafts", node_generate_lyrics_drafts)
workflow.add_node("refine_lyrics", node_refine_lyrics)
workflow.add_node("create_songs", node_create_songs)
workflow.add_node("assemble_video", node_assemble_video)
workflow.add_node("generate_metadata", node_generate_metadata)
workflow.add_node("upload_to_youtube", node_upload_to_youtube)
workflow.add_node("create_publication_report", node_create_publication_report)

workflow.set_conditional_entry_point(route_workflow)

# Flujo principal
workflow.add_edge("generate_song_plan", "generate_lyrics_drafts")

# Del borrador, decidimos si refinar o ir directo a crear la canción
workflow.add_conditional_edges(
    "generate_lyrics_drafts",
    should_refine_lyrics,
    {
        "refine_lyrics": "refine_lyrics",
        "create_songs": "create_songs"
    }
)

workflow.add_edge("refine_lyrics", "create_songs")
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
        """Busca archivos de forma recursiva y devuelve una lista de rutas."""
        if not os.path.exists(directory): 
            return []
        all_files = []
        for root, _, files in os.walk(directory):
            for f in files:
                if not f.startswith('.') and any(f.endswith(ext) for ext in extensions):
                    all_files.append(os.path.join(root, f))
        return all_files

    # 1. Inspeccionar el estado del sistema de archivos
    report_files = get_files_by_ext(PUBLICATION_REPORTS_DIR, ['.json'])
    if report_files:
        raise ValueError("Proceso ya completado. Se encontró un informe de publicación.")

    lyrics_files = get_files_by_ext(LYRICS_DIR, ['.txt'])
    song_files = get_files_by_ext(SONGS_DIR, ['.mp3'])
    clip_files = get_files_by_ext(CLIPS_DIR, ['.mp4', '.mov'])
    metadata_files = get_files_by_ext(METADATA_DIR, ['.json', '.txt'])
    final_video_exists = os.path.exists(VIDEO_OUTPUT_PATH)

    # 2. Construir el estado inicial
    state = AgentState(**initial_state)
    
    lyrics_files_sorted = sorted(lyrics_files, key=natural_sort_key)
    song_files_sorted = sorted(song_files, key=natural_sort_key)
    metadata_files_sorted = sorted(metadata_files, key=natural_sort_key)
    
    print("\n=== ARCHIVOS DETECTADOS PARA REANUDACIÓN ===")
    print(f"\n📝 Letras encontradas ({len(lyrics_files_sorted)}):")
    for idx, f in enumerate(lyrics_files_sorted, 1):
        print(f"  {idx}. {os.path.basename(f)}")
    
    print(f"\n🎵 Canciones encontradas ({len(song_files_sorted)}):")
    for idx, f in enumerate(song_files_sorted, 1):
        print(f"  {idx}. {os.path.basename(f)}")
    
    print(f"\n🎬 Clips de video encontrados ({len(clip_files)}):")
    for idx, f in enumerate(sorted(clip_files, key=natural_sort_key), 1):
        print(f"  {idx}. {os.path.basename(f)}")
    print("=============================================\n")
    
    state['draft_filepaths'] = lyrics_files_sorted # Asignar rutas de borradores para el refinamiento
    state['lyrics_list'] = [] # La lista de letras se llenará después del refinamiento
    
    state['song_paths'] = song_files_sorted
    state['final_video_path'] = VIDEO_OUTPUT_PATH if final_video_exists else None
    state['user_prompt'] = "Sesión Reanudada"
    state['song_style'] = "Estilo Reanudado"
    state['suno_model'] = initial_state.get('suno_model', 'chirp-auk-turbo')
    
    if metadata_files_sorted:
        state['metadata_path'] = metadata_files_sorted[0]
    else:
        state['metadata_path'] = None

    # 3. Determinar el punto de reanudación
    if final_video_exists and state['metadata_path']:
        state['resume_from_node'] = "upload_to_youtube"
        print("✅ Reanudando desde: Subida a YouTube (video y metadata listos)")
    elif final_video_exists:
        state['resume_from_node'] = "generate_metadata"
        print("✅ Reanudando desde: Generación de metadata (video listo)")
    elif lyrics_files_sorted and song_files_sorted:
        if not clip_files:
            raise ValueError("Faltan clips de video. Por favor, añade archivos .mp4 o .mov a la carpeta 'clips' para continuar.")
        state['resume_from_node'] = "assemble_video"
        print(f"✅ Reanudando desde: Ensamblaje de video ({len(song_files_sorted)} canciones listas)")
    elif lyrics_files_sorted:
        state['resume_from_node'] = "create_songs"
        print(f"✅ Reanudando desde: Creación de canciones ({len(lyrics_files_sorted)} letras listas para procesar)")
    else:
        raise ValueError("No hay suficiente progreso para reanudar. Inicia un nuevo proceso.")

    if state['resume_from_node'] == "assemble_video":
        # Llenar la lista de letras desde los archivos para el ensamblador
        for f in lyrics_files_sorted:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    content = file.read()
                    parsed_data = parse_lyrics_file(content)
                    state['lyrics_list'].append(parsed_data['prompt'])
            except Exception as e:
                print(f"⚠️ Advertencia: No se pudo leer {os.path.basename(f)}: {e}")

        if len(state['lyrics_list']) != len(state['song_paths']):
            print(f"⚠️ ADVERTENCIA: Discrepancia detectada!")
            print(f"   - Letras: {len(state['lyrics_list'])}")
            print(f"   - Canciones: {len(state['song_paths'])}")
            
            # NUNCA truncar las canciones - siempre usar TODAS
            # Solo ajustar las letras según si hay subtítulos o no
            if state.get('with_subtitles', True):
                # Con subtítulos: duplicar letras para que coincidan con las canciones
                if len(state['lyrics_list']) > 0:
                    num_songs = len(state['song_paths'])
                    num_lyrics = len(state['lyrics_list'])
                    
                    # Expandir letras de forma cíclica para cubrir todas las canciones
                    expanded_lyrics = []
                    for i in range(num_songs):
                        # Usar módulo para ciclar a través de las letras disponibles
                        lyric_index = i % num_lyrics
                        expanded_lyrics.append(state['lyrics_list'][lyric_index])
                    
                    state['lyrics_list'] = expanded_lyrics
                    print(f"   ✅ Letras expandidas a {len(state['lyrics_list'])} para subtítulos (cíclicamente)")
                else:
                    print(f"   ⚠️ No hay letras disponibles para subtítulos")
            else:
                # Sin subtítulos: vaciar la lista de letras (no se usarán)
                state['lyrics_list'] = []
                print(f"   ✅ Subtítulos desactivados, omitiendo letras")
            
            print(f"   ➡️ Video usará TODAS las {len(state['song_paths'])} canciones")

    print("\n🚀 Iniciando ejecución del workflow...\n")
    final_state = app_graph.invoke(state)
    print("\n--- Flujo de trabajo de reanudación completado ---")
    
    return {
        "youtube_url": final_state.get("youtube_url"),
        "video_path": final_state.get("final_video_path"),
    }
