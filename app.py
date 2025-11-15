
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from tasks import create_video_task, celery_app, resume_video_workflow_task
from celery.result import AsyncResult
from src.suno_api import SunoApiClient
from src.youtube_uploader import get_auth_flow, exchange_code_for_credentials
from src.config import (
    LYRICS_DIR, SONGS_DIR, CLIPS_DIR, OUTPUT_DIR, METADATA_DIR, 
    PUBLICATION_REPORTS_DIR, VIDEO_OUTPUT_PATH
)
import logging

class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        return record.getMessage().find('/v1/models') == -1

logging.getLogger("werkzeug").addFilter(HealthCheckFilter())


# --- Configuración de la aplicación Flask ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it-later')
app.config['SUNO_COOKIE'] = os.environ.get('SUNO_COOKIE', '')

# Rutas a las carpetas de salida, consistentes con config.py
OUTPUT_FOLDER = 'output'
SONGS_FOLDER = 'songs'

# --- Rutas de Autenticación de YouTube ---

@app.route('/authorize-youtube')
def authorize_youtube():
    """
    Inicia el flujo de autenticación de YouTube redirigiendo al usuario a Google.
    """
    try:
        flow = get_auth_flow()
        auth_uri = flow.step1_get_authorize_url()
        return redirect(auth_uri)
    except Exception as e:
        return f"Error al iniciar la autenticación: {e}", 500

@app.route('/oauth2callback')
def oauth2callback():
    """
    Callback de Google. Intercambia el código de autorización por credenciales.
    """
    code = request.args.get('code')
    if not code:
        return "Error: No se recibió el código de autorización de Google.", 400
    try:
        exchange_code_for_credentials(code)
        # Redirige a la página principal con un parámetro de éxito
        return redirect(url_for('index', auth_success='true'))
    except Exception as e:
        return f"Error al intercambiar el código por credenciales: {e}", 500

# --- Rutas de la aplicación web ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_prompt = request.form['prompt']
        song_style = request.form['style']
        llm_model = request.form.get('llm_model', 'openai/gpt-4o-mini')
        suno_model = request.form.get('suno_model', 'chirp-crow')
        is_instrumental = 'is_instrumental' in request.form
        language = request.form.get('language', 'spanish')
        with_subtitles = 'with_subtitles' in request.form
        
        num_female_songs = 0
        num_male_songs = 0
        num_instrumental_songs = 0

        if is_instrumental:
            num_instrumental_songs = int(request.form.get('num_instrumental_songs', 1))
        else:
            num_female_songs = int(request.form.get('num_female_songs', 0))
            num_male_songs = int(request.form.get('num_male_songs', 0))

        task = create_video_task.delay(
            user_prompt=user_prompt,
            song_style=song_style,
            is_instrumental=is_instrumental,
            language=language,
            with_subtitles=with_subtitles,
            num_female_songs=num_female_songs,
            num_male_songs=num_male_songs,
            num_instrumental_songs=num_instrumental_songs,
            llm_model=llm_model,
            suno_model=suno_model
        )
        return redirect(url_for('status', job_id=task.id))
    return render_template('index.html')

@app.route('/test')
def suno_test_page():
    return render_template('test.html')

@app.route('/status/<job_id>')
def status(job_id):
    return render_template('status.html', job_id=job_id)


@app.route('/resume', methods=['GET', 'POST'])
def resume():
    if request.method == 'POST':
        is_instrumental = 'instrumental' in request.form
        with_subtitles = 'subtitles' in request.form
        suno_model = request.form.get('suno_model', 'chirp-auk-turbo')
        task = resume_video_workflow_task.delay(
            is_instrumental=is_instrumental,
            with_subtitles=with_subtitles,
            suno_model=suno_model
        )
        return redirect(url_for('status', job_id=task.id))

    # Lógica para GET
    def get_file_count(directory, extensions):
        if not os.path.exists(directory):
            return 0
        return len([f for f in os.listdir(directory) if not f.startswith('.') and any(f.endswith(ext) for ext in extensions)])

    status_data = {
        'lyrics': {'count': get_file_count(LYRICS_DIR, ['.txt'])},
        'songs': {'count': get_file_count(SONGS_DIR, ['.mp3'])},
        'clips': {'count': get_file_count(CLIPS_DIR, ['.mp4', '.mov'])},
        'metadata': {'count': get_file_count(METADATA_DIR, ['.txt'])},
        'published': {'count': get_file_count(PUBLICATION_REPORTS_DIR, ['.json'])},
        'final_video': {'exists': os.path.exists(VIDEO_OUTPUT_PATH)}
    }

    return render_template('resume.html', status=status_data)


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
    try:
        task = celery_app.AsyncResult(job_id)

        if task.failed():
            response = {
                'state': 'FAILURE',
                'progress': '0%',
                'details': str(task.info),
            }
        elif task.state == 'PENDING':
            response = {
                'state': task.state,
                'progress': '0%',
                'details': 'La tarea está en la cola, esperando para empezar...'
            }
        elif task.state == 'SUCCESS':
            response = {
                'state': task.state,
                'progress': task.info.get('progress', '100%'),
                'details': task.info.get('details', 'Completado'),
                'result': task.info
            }
        else:  # Otros estados como STARTED o PROGRESS
            response = {
                'state': task.state,
                'progress': task.info.get('progress', '0%'),
                'details': task.info.get('details', '')
            }
    except Exception as e:
        # Si ocurre cualquier error al consultar el estado (como el KeyError),
        # devolvemos una respuesta de fallo genérica para no romper la UI.
        app.logger.error(f"Error al obtener el estado de la tarea {job_id}: {e}")
        response = {
            'state': 'FAILURE',
            'progress': '0%',
            'details': 'Error interno al obtener el estado de la tarea. Revisa los logs del worker.',
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

@app.route('/v1/models', methods=['GET'])
def get_models():
    return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
