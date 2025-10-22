
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from tasks import create_video_task, celery_app
from celery.result import AsyncResult
from src.suno_api import SunoApiClient

# --- Configuración de la aplicación Flask ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it-later')
app.config['SUNO_COOKIE'] = os.environ.get('SUNO_COOKIE', '')

# Rutas a las carpetas de salida, consistentes con config.py
OUTPUT_FOLDER = 'output'
SONGS_FOLDER = 'songs'

# --- Rutas de la aplicación web ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_prompt = request.form['prompt']
        song_style = request.form['style']
        num_female_songs = int(request.form.get('num_female_songs', 0))
        num_male_songs = int(request.form.get('num_male_songs', 0))
        task = create_video_task.delay(user_prompt, song_style, num_female_songs, num_male_songs)
        return redirect(url_for('status', job_id=task.id))
    return render_template('index.html')

@app.route('/test')
def suno_test_page():
    return render_template('test.html')

@app.route('/status/<job_id>')
def status(job_id):
    return render_template('status.html', job_id=job_id)

# --- Rutas de API --- #

@app.route('/api/suno-custom-check')
def suno_custom_check_api():
    try:
        client = SunoApiClient()
        client.check_connection()
        return jsonify({'success': True, 'message': 'Conexión con Suno API exitosa.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/status/<job_id>')
def job_status_api(job_id):
    task = celery_app.AsyncResult(job_id)
    
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


@app.route('/api/test-suno-custom-generate', methods=['POST'])
def test_suno_custom_generate_api():
    data = request.get_json()
    
    # Get all possible fields from the form
    tags = data.get('tags', '')
    title = data.get('title', '')
    prompt = data.get('prompt', '')
    vocal_gender = data.get('vocal_gender', 'f')

    # Determine if an instrumental should be made
    # This is true if the prompt is empty or just whitespace.
    make_instrumental = not bool(prompt and prompt.strip())

    # Validation
    if not tags:
        return jsonify({'error': 'Estilo Musical / Descripción es un campo requerido.'}), 400
    if not make_instrumental and not title:
        return jsonify({'error': 'Título es requerido para canciones con voz.'}), 400

    try:
        client = SunoApiClient()
        generation_response = client.generate(
            tags=tags,
            title=title,
            prompt=prompt,
            make_instrumental=make_instrumental,
            vocal_gender=vocal_gender
        )
        song_ids = [clip['id'] for clip in generation_response['clips']]
        final_songs = client.poll_for_song(song_ids)
        return jsonify(final_songs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
