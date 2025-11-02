import os
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip, concatenate_audioclips, vfx
from src.config import CLIPS_DIR, VIDEO_OUTPUT_PATH, OUTPUT_DIR
from celery import Task


def crossfade_concatenate(clips, duration):
    """
    Concatena clips con efecto de crossfade usando MoviePy 2.0+ API.
    """
    if not clips:
        return None
    
    if len(clips) == 1:
        return clips[0]

    # MoviePy 2.0+ usa .with_effects() en lugar de .fx()
    faded_clips = [clips[0].with_effects([vfx.CrossFadeOut(duration)])]
    
    for clip in clips[1:-1]:
        faded_clips.append(
            clip.with_effects([
                vfx.CrossFadeIn(duration),
                vfx.CrossFadeOut(duration)
            ])
        )
    
    faded_clips.append(clips[-1].with_effects([vfx.CrossFadeIn(duration)]))

    # Concatenar clips con padding negativo para el crossfade
    return concatenate_videoclips(faded_clips, padding=-duration, method="compose")


def loop_video_to_duration(video_clip, target_duration):
    """
    Hace loop de un video hasta alcanzar la duración objetivo.
    Alternativa robusta a vfx.Loop que tiene bugs conocidos.
    """
    if video_clip.duration >= target_duration:
        return video_clip.subclipped(0, target_duration)
    
    # Calcular cuántas repeticiones necesitamos
    num_loops = int(target_duration / video_clip.duration) + 1
    
    # Crear lista de clips repetidos
    repeated_clips = [video_clip] * num_loops
    
    # Concatenar y recortar a la duración exacta
    looped = concatenate_videoclips(repeated_clips, method="compose")
    return looped.subclipped(0, target_duration)


def get_system_font_path():
    """
    Obtiene la ruta a una fuente del sistema según la plataforma.
    MoviePy 2.0+ requiere ruta completa al archivo de fuente.
    """
    import platform
    import glob
    
    system = platform.system()
    
    # Intentar encontrar Arial o fuentes comunes
    font_paths = {
        'Darwin': [
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            '/Library/Fonts/Arial.ttf'
        ],
        'Linux': [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'
        ],
        'Windows': [
            'C:\\Windows\\Fonts\\arialbd.ttf',
            'C:\\Windows\\Fonts\\arial.ttf'
        ]
    }
    
    # Buscar la primera fuente que existe
    for font_path in font_paths.get(system, []):
        if os.path.exists(font_path):
            return font_path
    
    # Fallback: buscar cualquier fuente .ttf
    if system == 'Linux':
        ttf_files = glob.glob('/usr/share/fonts/**/*.ttf', recursive=True)
        if ttf_files:
            return ttf_files[0]
    
    # Última opción: devolver None y capturar el error más adelante
    return None


def assemble_video(
    song_paths: list[str], 
    lyrics_list: list[str], 
    with_subtitles: bool = True,
    task_instance: Task = None
) -> str:
    """
    Ensambla el video final usando MoviePy 2.0+ API.
    Compatible con las últimas versiones de MoviePy.
    """
    def update_status(details: str):
        print(details)
        if task_instance:
            try:
                current_progress = int(task_instance.info.get('progress', '0').replace('%', ''))
                task_instance.update_state(
                    state='PROGRESS',
                    meta={'details': details, 'progress': f'{current_progress}%'}
                )
            except Exception as e:
                print(f"Error actualizando estado de tarea: {e}")

    update_status("Iniciando ensamblaje de video...")

    clips = []
    audio_clips = []
    source_video = None
    final_video_base = None
    final_composition = None
    subtitle_clips = []

    try:
        # 1. Validar y cargar clips de video
        if not os.path.exists(CLIPS_DIR) or not os.listdir(CLIPS_DIR):
            raise FileNotFoundError(f"No se encontraron videoclips en la carpeta '{CLIPS_DIR}'.")
        
        video_files = [
            os.path.join(CLIPS_DIR, f) 
            for f in os.listdir(CLIPS_DIR) 
            if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))
        ]
        
        if not video_files:
            raise FileNotFoundError(
                f"No se encontraron archivos de video compatibles en '{CLIPS_DIR}'."
            )

        update_status(f"Cargando {len(video_files)} clips de video...")
        
        # Cargar clips de video sin audio
        clips = [VideoFileClip(vf).without_audio() for vf in video_files]
        output_fps = clips[0].fps if clips and clips[0].fps else 30

        # 2. Cargar y concatenar audio
        update_status(f"Procesando {len(song_paths)} archivos de audio...")
        audio_clips = [AudioFileClip(sp) for sp in song_paths]
        final_audio = concatenate_audioclips(audio_clips)
        total_duration = final_audio.duration

        update_status(f"Duración total del audio: {total_duration:.2f} segundos")

        # 3. Crear super clip con transiciones
        update_status("Creando video base con transiciones...")
        source_video = crossfade_concatenate(clips, 1)

        # 4. Hacer loop del video hasta la duración del audio
        update_status("Haciendo loop del video para igualar duración del audio...")
        final_video_base = loop_video_to_duration(source_video, total_duration)
        
        # 5. Asignar el audio al video
        final_video_base = final_video_base.with_audio(final_audio)

        # 6. Añadir subtítulos si está habilitado
        if with_subtitles:
            update_status("Generando subtítulos...")
            
            # Obtener ruta a fuente del sistema
            font_path = get_system_font_path()
            
            if font_path is None:
                update_status("ADVERTENCIA: No se encontró fuente del sistema, omitiendo subtítulos.")
                final_composition = final_video_base
            else:
                update_status(f"Usando fuente: {font_path}")
                
                try:
                    from moviepy import TextClip
                    
                    audio_start_time = 0
                    for i, lyrics in enumerate(lyrics_list):
                        song_duration = audio_clips[i].duration
                        lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
                        
                        if not lines:
                            continue

                        time_per_line = song_duration / len(lines)

                        for j, line in enumerate(lines):
                            # MoviePy 2.0+ API para TextClip
                            txt_clip = (
                                TextClip(
                                    font=font_path,  # Primer argumento: ruta a fuente
                                    text=line,
                                    font_size=40,  # font_size en lugar de fontsize
                                    color='white',
                                    stroke_color='black',
                                    stroke_width=2,
                                    size=final_video_base.size,
                                    method='caption'
                                )
                                .with_position(('center', 'bottom'))
                                .with_start(audio_start_time + j * time_per_line)
                                .with_duration(time_per_line)
                            )
                            
                            # Aplicar efectos de fade
                            txt_clip = txt_clip.with_effects([
                                vfx.CrossFadeIn(0.3),
                                vfx.CrossFadeOut(0.3)
                            ])
                            
                            subtitle_clips.append(txt_clip)
                        
                        audio_start_time += song_duration
                    
                    update_status(f"Se crearon {len(subtitle_clips)} clips de subtítulos")
                    final_composition = CompositeVideoClip([final_video_base] + subtitle_clips)
                    
                except Exception as subtitle_error:
                    update_status(f"Error generando subtítulos: {subtitle_error}")
                    update_status("Continuando sin subtítulos...")
                    final_composition = final_video_base
        else:
            update_status("Omitiendo la generación de subtítulos.")
            final_composition = final_video_base

        # 7. Escribir el archivo final
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        update_status("Renderizando el video final (esto puede tardar)...")
        
        final_composition.write_videofile(
            VIDEO_OUTPUT_PATH,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=os.path.join(OUTPUT_DIR, "temp-audio.m4a"),
            remove_temp=True,
            threads=4,
            fps=output_fps,
            logger='bar',
            preset='medium'  # Preset para mejor balance velocidad/calidad
        )
        
        update_status("¡Video renderizado exitosamente!")
        return VIDEO_OUTPUT_PATH
        
    except Exception as e:
        error_msg = f"Error durante el ensamblaje del video: {type(e).__name__}: {str(e)}"
        print(error_msg)
        update_status(error_msg)
        raise
        
    finally:
        # 8. Liberar memoria de todos los clips
        update_status("Liberando recursos...")
        try:
            for clip in clips:
                clip.close()
            for clip in audio_clips:
                clip.close()
            if subtitle_clips:
                for clip in subtitle_clips:
                    clip.close()
            if source_video:
                source_video.close()
            if final_video_base:
                final_video_base.close()
            if final_composition:
                final_composition.close()
        except Exception as cleanup_error:
            print(f"Error limpiando recursos: {cleanup_error}")