
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from tasks import create_video_task
from celery.result import AsyncResult

# --- Configuración de la aplicación Flask ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it-later')

# Rutas a las carpetas de salida, consistentes con config.py
OUTPUT_FOLDER = 'output'
SONGS_FOLDER = 'songs'

# --- Rutas de la aplicación web ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 1. Recoger los datos del formulario
        user_prompt = request.form['prompt']
        song_style = request.form['style']
        num_songs = int(request.form['num_songs'])

        # 2. Lanzar la tarea de Celery en segundo plano
        task = create_video_task.delay(user_prompt, song_style, num_songs)

        # 3. Redirigir al usuario a la página de estado, pasando el ID de la tarea
        return redirect(url_for('status', job_id=task.id))
        
    return render_template('index.html')

@app.route('/status/<job_id>')
def status(job_id):
    # Renderiza la página que sondeará el estado de la tarea
    return render_template('status.html', job_id=job_id)

@app.route('/api/status/<job_id>')
def job_status_api(job_id):
    # API que el frontend consulta para obtener el progreso de la tarea
    task = AsyncResult(job_id)
    
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'progress': '0%',
            'details': 'La tarea está en la cola, esperando para empezar...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'progress': task.info.get('progress', '0%'),
            'details': task.info.get('details', '')
        }
        # Si la tarea ha terminado con éxito (SUCCESS), el resultado estará en task.info
        if task.state == 'SUCCESS':
             response['result'] = task.info
    else:
        # El estado es FAILURE
        response = {
            'state': task.state,
            'progress': '0%',
            'details': str(task.info),  # task.info contiene la excepción
        }

    return jsonify(response)

# --- Rutas para servir archivos generados ---

@app.route('/videos/<path:filename>')
def serve_video(filename):
    # Sirve el video final desde la carpeta 'output'
    return send_from_directory(os.path.join(os.getcwd(), OUTPUT_FOLDER), filename, as_attachment=False)

@app.route('/songs/<path:filename>')
def serve_song(filename):
    # Sirve las canciones generadas desde la carpeta 'songs'
    return send_from_directory(os.path.join(os.getcwd(), SONGS_FOLDER), filename, as_attachment=False)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
