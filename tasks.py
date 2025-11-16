import sys
import os
import logging

# --- Inyectar la librería local de Suno ---
project_root = os.path.abspath(os.path.dirname(__file__))
local_suno_path = os.path.join(project_root, 'local_libs', 'SunoAI')
if local_suno_path not in sys.path:
    sys.path.insert(0, local_suno_path)
# --- Fin de la inyección ---

# Añade el directorio raíz del proyecto a la ruta de Python
# para asegurar que Celery encuentre los módulos de 'src'.
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery import Celery, Task
from src.main_orchestrator import (
    resume_video_workflow, 
    node_generate_song_plan,
    node_generate_lyrics_drafts, 
    node_refine_lyrics
)
from src.suno_api import SunoApiClient

# --- Configuración de Logging ---
# Esto nos ayuda a ver los errores de Celery de forma más clara.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuración de la aplicación Celery ---
# Definimos la aplicación Celery, apuntando a Redis como intermediario.
# El 'main' es el nombre del módulo actual, es una convención de Celery.
celery_app = Celery('tasks',
                    broker='redis://localhost:6379/1',
                    backend='redis://localhost:6379/1')

# Opcional: Configuración adicional de Celery para mayor robustez
celery_app.conf.update(
    task_track_started=True,
    result_extended=True
)

# --- Definición de la Tarea de Celery ---

@celery_app.task(bind=True)
def create_video_task(self, user_prompt, song_style, is_instrumental, language, with_subtitles, refine_lyrics, num_female_songs, num_male_songs, num_instrumental_songs, llm_model, suno_model):
    """
    Tarea de Celery que genera los borradores de letras y se detiene,
    permitiendo la revisión manual del usuario.
    """
    try:
        self.update_state(state='STARTED', meta={'details': 'Iniciando la generación de letras...'})
        
        client = SunoApiClient()
        client.initialize_session()

        initial_state = {
            "user_prompt": user_prompt, "song_style": song_style,
            "is_instrumental": is_instrumental, "language": language,
            "with_subtitles": with_subtitles, "refine_lyrics": refine_lyrics,
            "num_female_songs": num_female_songs, "num_male_songs": num_male_songs,
            "num_instrumental_songs": num_instrumental_songs,
            "llm_model": llm_model, "suno_model": suno_model,
            "task_instance": self, "suno_client": client
        }

        # 1. Generar el PLAN de canciones
        plan_state = node_generate_song_plan(initial_state)
        current_state = {**initial_state, **plan_state}

        # 2. Generar los BORRADORES de letras usando el plan
        draft_state = node_generate_lyrics_drafts(current_state)
        current_state.update(draft_state)

        # 3. Refinar las letras si el usuario lo solicitó
        if refine_lyrics and not is_instrumental:
            refine_state = node_refine_lyrics(current_state)
            current_state.update(refine_state)
        
        self.update_state(state='PROGRESS', meta={'details': 'Letras generadas. Proceso en pausa para revisión manual.', 'progress': '100%'})

        return {
            'state': 'SUCCESS',
            'details': 'Letras generadas y listas para su revisión. Por favor, ve a la página de "Reanudar Proceso" para editar y continuar.',
            'result': 'LYRICS_GENERATED'
        }

    except Exception as e:
        logger.error(f"La tarea de generación de letras ha fallado: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'details': str(e)})
        return {'state': 'FAILURE', 'details': str(e)}


@celery_app.task(bind=True)
def resume_video_workflow_task(self, is_instrumental, with_subtitles, suno_model, llm_model):
    """
    Tarea de Celery para reanudar el proceso de creación de video.
    """
    try:
        self.update_state(state='STARTED', meta={'details': 'Reanudando el proceso...'})
        
        client = SunoApiClient()
        client.initialize_session() # Pre-autenticar al inicio de la tarea

        initial_state = {
            "is_instrumental": is_instrumental,
            "with_subtitles": with_subtitles,
            "suno_model": suno_model,
            "llm_model": llm_model,
            "task_instance": self,
            "suno_client": client # Pasamos el cliente instanciado
        }

        final_result = resume_video_workflow(initial_state)

        return {
            'state': 'SUCCESS',
            'details': '¡Proceso de reanudación completado!',
            'result': final_result
        }

    except Exception as e:
        logger.error(f"La tarea de reanudación ha fallado: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'details': str(e)})
        return {'state': 'FAILURE', 'details': str(e)}


@celery_app.task(bind=True)
def test_sunoai_generate(self, prompt: str):
    """Una tarea de prueba para verificar la generación con la nueva librería SunoAI."""
    try:
        from suno import Suno
        from src.config import SUNO_COOKIE

        self.update_state(state='STARTED', meta={'details': 'Iniciando prueba de generación con SunoAI...'})
        
        client = Suno(cookie=SUNO_COOKIE)
        
        self.update_state(state='PROGRESS', meta={'details': 'Cliente SunoAI inicializado. Enviando a generar...'})

        # Usamos el modo "description" (no custom) para la prueba más simple
        songs = client.generate(prompt=prompt, is_custom=False, wait_audio=True)
        
        # Si llegamos aquí, ¡éxito!
        song_ids = [song.id for song in songs]
        result = {'success': True, 'song_ids': song_ids}
        self.update_state(state='SUCCESS', meta=result)
        return result

    except Exception as e:
        logger.error(f"La tarea de prueba de SunoAI ha fallado: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'details': str(e)})
        return {'state': 'FAILURE', 'details': str(e)}
