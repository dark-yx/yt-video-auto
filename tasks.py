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
from src.main_orchestrator import run_video_workflow, resume_video_workflow

# --- Configuración de Logging ---
# Esto nos ayuda a ver los errores de Celery de forma más clara.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuración de la aplicación Celery ---
# Definimos la aplicación Celery, apuntando a Redis como intermediario.
# El 'main' es el nombre del módulo actual, es una convención de Celery.
celery_app = Celery('tasks',
                    broker='redis://localhost:6379/0',
                    backend='redis://localhost:6379/0')

# Opcional: Configuración adicional de Celery para mayor robustez
celery_app.conf.update(
    task_track_started=True,
    result_extended=True
)

# --- Definición de la Tarea de Celery ---

@celery_app.task(bind=True)
def create_video_task(self, user_prompt, song_style, num_female_songs, num_male_songs):
    """
    Esta es la tarea de Celery que se ejecuta en segundo plano.
    'bind=True' hace que la instancia de la tarea (self) esté disponible,
    lo que es crucial para actualizar el estado.
    """
    try:
        self.update_state(state='STARTED', meta={'details': 'Iniciando el proceso...'})
        
        initial_state = {
            "user_prompt": user_prompt,
            "song_style": song_style,
            "num_female_songs": num_female_songs,
            "num_male_songs": num_male_songs,
            "task_instance": self  # Pasamos la instancia de la tarea al estado
        }

        # Llamamos a nuestra lógica principal del orquestador.
        # run_video_workflow ahora aceptará la instancia de la tarea (self).
        final_result = run_video_workflow(initial_state)

        # Si todo va bien, el estado final es SUCCESS
        # y el resultado contiene la información del video final.
        return {
            'state': 'SUCCESS',
            'details': '¡Video completado y subido!',
            'result': final_result
        }

    except Exception as e:
        logger.error(f"La tarea ha fallado: {e}", exc_info=True)
        # Si algo sale mal, actualizamos el estado a FAILURE.
        self.update_state(state='FAILURE', meta={'details': str(e)})
        # Esto es útil para manejar excepciones de forma explícita.
        return {'state': 'FAILURE', 'details': str(e)}


@celery_app.task(bind=True)
def resume_video_workflow_task(self, is_instrumental, with_subtitles):
    """
    Tarea de Celery para reanudar el proceso de creación de video.
    """
    try:
        self.update_state(state='STARTED', meta={'details': 'Reanudando el proceso...'})
        
        initial_state = {
            "is_instrumental": is_instrumental,
            "with_subtitles": with_subtitles,
            "task_instance": self
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
