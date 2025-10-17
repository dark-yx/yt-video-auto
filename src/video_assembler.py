
import os
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips, 
    AudioFileClip, CompositeAudioClip, 
    TextClip, CompositeVideoClip
)
from src.config import CLIPS_DIR, VIDEO_OUTPUT_PATH

def assemble_video(
    song_paths: list[str], 
    lyrics_list: list[str], 
    num_songs: int
) -> str:
    """
    Ensambla el video final a partir de videoclips, canciones y letras.
    Devuelve la ruta al archivo de video final.
    """
    print("Iniciando el ensamblaje del video...")
    
    # 1. Cargar videoclips de origen
    try:
        video_files = [os.path.join(CLIPS_DIR, f) for f in os.listdir(CLIPS_DIR) if f.endswith(".mp4")]
        if not video_files:
            print("¡Error: No se encontraron videoclips en la carpeta src/clips!")
            return ""
        clips = [VideoFileClip(vf) for vf in video_files]
    except Exception as e:
        print(f"Error al cargar los videoclips: {e}")
        return ""

    # 2. Cargar y concatenar pistas de audio
    try:
        audio_clips = [AudioFileClip(sp) for sp in song_paths]
        final_audio = concatenate_audioclips(audio_clips)
        total_duration = final_audio.duration
    except Exception as e:
        print(f"Error al procesar los clips de audio: {e}")
        return ""

    # 3. Repetir los videoclips para que coincidan con la duración del audio
    video_segments = []
    current_duration = 0
    clip_index = 0
    while current_duration < total_duration:
        clip = clips[clip_index % len(clips)]
        video_segments.append(clip)
        current_duration += clip.duration
        clip_index += 1
    
    final_video = concatenate_videoclips(video_segments).set_duration(total_duration)
    final_video = final_video.set_audio(final_audio)

    # 4. Crear y superponer subtítulos animados
    subtitle_clips = []
    audio_start_time = 0
    for i, lyrics in enumerate(lyrics_list):
        song_duration = audio_clips[i].duration
        lines = [line for line in lyrics.split('\n') if line.strip()]
        time_per_line = song_duration / len(lines) if lines else 0

        for j, line in enumerate(lines):
            txt_clip = (
                TextClip(
                    line, 
                    fontsize=40, 
                    color='white', 
                    font='Arial-Bold', 
                    stroke_color='black', 
                    stroke_width=1.5
                )
                .set_position(('center', 'bottom'))
                .set_start(audio_start_time + j * time_per_line)
                .set_duration(time_per_line)
                .crossfadein(0.5)
                .crossfadeout(0.5)
            )
            subtitle_clips.append(txt_clip)
        
        audio_start_time += song_duration

    # Combinar video y subtítulos
    final_composition = CompositeVideoClip([final_video] + subtitle_clips)

    # 5. Escribir el video final en el archivo
    try:
        print(f"Escribiendo el video final en {VIDEO_OUTPUT_PATH}...")
        final_composition.write_videofile(
            VIDEO_OUTPUT_PATH, 
            codec="libx264", 
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            threads=4 # Aumentar para una representación más rápida
        )
        print("¡Ensamblaje de video completado!")
        return VIDEO_OUTPUT_PATH
    except Exception as e:
        print(f"Error al escribir el archivo de video final: {e}")
        return ""
