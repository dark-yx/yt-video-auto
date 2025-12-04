
import os
import sys
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Añadir directorio raíz al path
sys.path.append(os.getcwd())

from src.video_assembler import assemble_video

print("Iniciando prueba de ensamblaje de video...")

# Mock de la tarea de Celery
class MockTask:
    def update_state(self, state, meta):
        print(f"Celery State Update: {state} - {meta}")

try:
    # Llamar a la función directamente
    # Pasamos listas vacías porque la función ahora escanea los directorios por sí misma
    # y maneja la ausencia de letras/subtítulos
    output_path = assemble_video(
        song_paths=[], 
        lyrics_list=[], 
        with_subtitles=False, # Probamos sin subtítulos primero para aislar el problema de duración
        task_instance=MockTask()
    )
    print(f"Video generado en: {output_path}")
    
    # Verificar duración con ffprobe
    import subprocess
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"Duración final del video: {result.stdout.strip()} segundos")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
