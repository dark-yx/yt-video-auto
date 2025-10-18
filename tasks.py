
import os
import logging
from celery import Celery, Task
from src.main_orchestrator import run_video_workflow

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
def create_video_task(self, user_prompt, song_style, num_songs):
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
            "num_songs": num_songs,
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
