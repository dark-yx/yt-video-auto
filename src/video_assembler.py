
import os
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, TextClip, CompositeVideoClip
from src.config import CLIPS_DIR, VIDEO_OUTPUT_PATH, OUTPUT_DIR
from celery import Task

def assemble_video(
    song_paths: list[str], 
    lyrics_list: list[str], 
    task_instance: Task = None
) -> str:
    """
    Ensambla el video final, informando del progreso a Celery.
    """
    def update_status(details: str):
        print(details)
        if task_instance:
            current_progress = int(task_instance.info.get('progress', '0').replace('%', ''))
            task_instance.update_state(
                state='PROGRESS',
                meta={'details': details, 'progress': f'{current_progress}%'}
            )

    update_status("Iniciando ensamblaje de video...")

    try:
        # CORREGIDO: Usar la variable CLIPS_DIR directamente de la configuración
        if not os.path.exists(CLIPS_DIR) or not os.listdir(CLIPS_DIR):
            raise FileNotFoundError(f"No se encontraron videoclips en la carpeta '{CLIPS_DIR}'. Por favor, añade archivos de video (.mp4, .mov) a esa carpeta.")
        
        video_files = [os.path.join(CLIPS_DIR, f) for f in os.listdir(CLIPS_DIR) if f.endswith((".mp4", ".mov"))]
        if not video_files:
            raise FileNotFoundError(f"No se encontraron archivos de video compatibles (.mp4, .mov) en la carpeta '{CLIPS_DIR}'.")

        clips = [VideoFileClip(vf) for vf in video_files]
        
        audio_clips = [AudioFileClip(sp) for sp in song_paths]
        final_audio = concatenate_audioclips(audio_clips)
        total_duration = final_audio.duration

        # Crear un bucle de videoclips para que coincida con la duración del audio
        video_segments = []
        current_duration = 0
        clip_index = 0
        while current_duration < total_duration:
            clip = clips[clip_index % len(clips)]
            # Si el clip es más largo que el tiempo restante, lo cortamos
            if current_duration + clip.duration > total_duration:
                clip = clip.subclip(0, total_duration - current_duration)
            video_segments.append(clip)
            current_duration += clip.duration
            clip_index += 1
        
        final_video_base = concatenate_videoclips(video_segments).set_duration(total_duration)
        final_video_base = final_video_base.set_audio(final_audio)

        # Añadir subtítulos
        subtitle_clips = []
        audio_start_time = 0
        for i, lyrics in enumerate(lyrics_list):
            song_duration = audio_clips[i].duration
            lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
            
            if not lines:
                continue # No hay letras para esta canción, saltar

            time_per_line = song_duration / len(lines)

            for j, line in enumerate(lines):
                txt_clip = (
                    TextClip(
                        line, fontsize=40, color='white', font='Arial-Bold',
                        stroke_color='black', stroke_width=1.5, method='caption', size=final_video_base.size
                    )
                    .set_position(('center', 'bottom'))
                    .set_start(audio_start_time + j * time_per_line)
                    .set_duration(time_per_line)
                    .crossfadein(0.3).crossfadeout(0.3)
                )
                subtitle_clips.append(txt_clip)
            audio_start_time += song_duration

        final_composition = CompositeVideoClip([final_video_base] + subtitle_clips)

        # Asegurarse de que el directorio de salida exista
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        update_status("Renderizando el video final...")
        final_composition.write_videofile(
            VIDEO_OUTPUT_PATH, 
            codec="libx264", 
            audio_codec="aac",
            temp_audiofile=os.path.join(OUTPUT_DIR, "temp-audio.m4a"),
            remove_temp=True,
            threads=4, # Usar múltiples hilos para acelerar
            logger='bar' # Muestra una barra de progreso en la consola
        )
        
        # Liberar memoria
        for clip in clips + audio_clips + video_segments + subtitle_clips:
            clip.close()
        final_video_base.close()
        final_composition.close()

        return VIDEO_OUTPUT_PATH
    except Exception as e:
        print(f"Error durante el ensamblaje del video: {e}")
        raise
