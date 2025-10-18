
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from tasks import create_video_task
from celery.result import AsyncResult

# --- Configuración de la aplicación Flask ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it-later')

# --- Rutas de la aplicación web ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 1. Recoger los datos del formulario
        user_prompt = request.form['prompt']
        song_style = request.form['style']
        num_songs = int(request.form['num_songs'])

        # 2. Lanzar la tarea de Celery en segundo plano
        # .delay() es la forma de llamar a una tarea para que se ejecute en el worker
        task = create_video_task.delay(user_prompt, song_style, num_songs)

        # 3. Redirigir al usuario a la página de estado, pasando el ID de la tarea
        return redirect(url_for('status', job_id=task.id))
        
    return render_template('index.html')

@app.route('/status/<job_id>')
def status(job_id):
    # Simplemente renderizamos la página de estado, el frontend se encargará del resto
    return render_template('status.html', job_id=job_id)

@app.route('/api/status/<job_id>')
def job_status_api(job_id):
    # Esta es la API clave que el frontend consulta (sondea)
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
        if 'result' in task.info:
             response['result'] = task.info['result']
    else:
        # El estado es FAILURE
        response = {
            'state': task.state,
            'progress': '0%',
            'details': str(task.info),  # task.info contiene la excepción
        }

    return jsonify(response)


@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(os.path.join(app.root_path, 'videos'), filename)

@app.route('/songs/<path:filename>')
def serve_song(filename):
    return send_from_directory(os.path.join(app.root_path, 'songs'), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
