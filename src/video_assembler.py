
import os
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips, 
    AudioFileClip, CompositeAudioClip, 
    TextClip, CompositeVideoClip
)
from src.config import CLIPS_DIR, VIDEO_OUTPUT_PATH
from celery import Task

def assemble_video(
    song_paths: list[str], 
    lyrics_list: list[str], 
    num_songs: int,
    task_instance: Task = None
) -> str:
    """
    Ensambla el video final, informando del progreso a Celery.
    Devuelve la ruta al archivo de video final o lanza una excepción si falla.
    """
    def update_status(details: str):
        print(details)
        if task_instance:
            current_progress = int(task_instance.info.get('progress', '0').replace('%', ''))
            task_instance.update_state(
                state='PROGRESS',
                meta={'details': details, 'progress': f'{current_progress}%'}
            )

    update_status("Iniciando el ensamblaje del video: cargando clips de origen...")

    # 1. Cargar videoclips de origen
    try:
        video_files = [os.path.join(CLIPS_DIR, f) for f in os.listdir(CLIPS_DIR) if f.endswith((".mp4", ".mov"))]
        if not video_files:
            raise FileNotFoundError("¡Error: No se encontraron videoclips (.mp4, .mov) en la carpeta src/clips!")
        clips = [VideoFileClip(vf) for vf in video_files]
    except Exception as e:
        print(f"Error al cargar los videoclips: {e}")
        raise

    # 2. Cargar y concatenar pistas de audio
    update_status("Procesando y concatenando las pistas de audio generadas...")
    try:
        audio_clips = [AudioFileClip(sp) for sp in song_paths]
        final_audio = concatenate_audioclips(audio_clips)
        total_duration = final_audio.duration
    except Exception as e:
        print(f"Error al procesar los clips de audio: {e}")
        raise

    # 3. Preparar videoclips y subtítulos
    update_status("Calculando la disposición del video y preparando los subtítulos...")
    video_segments = []
    current_duration = 0
    clip_index = 0
    while current_duration < total_duration:
        clip = clips[clip_index % len(clips)]
        video_segments.append(clip)
        current_duration += clip.duration
        clip_index += 1
    
    final_video_base = concatenate_videoclips(video_segments).set_duration(total_duration)
    final_video_base = final_video_base.set_audio(final_audio)

    subtitle_clips = []
    audio_start_time = 0
    for i, lyrics in enumerate(lyrics_list):
        song_duration = audio_clips[i].duration
        lines = [line for line in lyrics.split('\n') if line.strip()]
        time_per_line = (song_duration / len(lines)) if lines else 0

        for j, line in enumerate(lines):
            txt_clip = (
                TextClip(
                    line, fontsize=40, color='white', font='Arial-Bold',
                    stroke_color='black', stroke_width=1.5
                )
                .set_position(('center', 'bottom'))
                .set_start(audio_start_time + j * time_per_line)
                .set_duration(time_per_line)
                .crossfadein(0.5).crossfadeout(0.5)
            )
            subtitle_clips.append(txt_clip)
        audio_start_time += song_duration

    final_composition = CompositeVideoClip([final_video_base] + subtitle_clips)

    # 4. Escribir el video final (la parte más lenta)
    update_status("Renderizando el video final. Este es el paso más largo, por favor espere...")
    try:
        final_composition.write_videofile(
            VIDEO_OUTPUT_PATH, 
            codec="libx264", 
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            threads=4, # Usar múltiples hilos para acelerar
            logger=None # Desactivar el logger de moviepy para no saturar la consola
        )
        print("¡Ensamblaje de video completado!")
        return VIDEO_OUTPUT_PATH
    except Exception as e:
        print(f"Error catastrófico al escribir el archivo de video final: {e}")
        raise
