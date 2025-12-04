import os
import subprocess
import json
import math
from pathlib import Path
from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, vfx, concatenate_audioclips
from src.config import CLIPS_DIR, VIDEO_OUTPUT_PATH, OUTPUT_DIR
from celery import Task

# --- Configuración de Rendimiento ---
PERFORMANCE_CONFIG = {
    'codec': 'h264_videotoolbox',
    'bitrate': '5000k',
    'audio_codec': 'aac',
    'audio_bitrate': '128k',
    'threads': 2,
    'fps': 24,
    'subtitle_font_size': 32,
    'subtitle_stroke_width': 1,
    'subtitle_fade_duration': 0.2,
    'subtitle_method': 'label',
    'max_subtitle_cache': 50,
    'cleanup_temp_files': True
}

# --- Funciones Auxiliares ---

def _get_duration_ffprobe(file_path):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', file_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(json.loads(result.stdout)['format']['duration'])
    except Exception:
        clip = AudioFileClip(file_path) if str(file_path).endswith(('.mp3', '.aac')) else VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration

def get_system_font_path():
    import platform, glob
    system = platform.system()
    font_paths = {
        'Darwin': ['/System/Library/Fonts/Supplemental/Arial.ttf'],
        'Linux': ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
        'Windows': ['C:\\Windows\\Fonts\\arial.ttf']
    }
    for font_path in font_paths.get(system, []):
        if os.path.exists(font_path): return font_path
    return None

# --- Motor FFmpeg ---

def _ffmpeg_concatenate_files(files, output_path, file_type):
    temp_dir = Path(OUTPUT_DIR) / "temp_ffmpeg"
    temp_dir.mkdir(parents=True, exist_ok=True)
    list_path = temp_dir / f"concat_{file_type}_{os.getpid()}.txt"
    with open(list_path, 'w') as f:
        for file in files:
            # Escapar comillas simples en la ruta del archivo para el formato de lista de FFmpeg
            safe_path = os.path.abspath(file).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
    cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', str(list_path), '-c', 'copy', '-y', str(output_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path
    finally:
        if list_path.exists(): list_path.unlink()

def _ffmpeg_loop_video_smart(video_path, audio_path, output_path):
    video_duration = _get_duration_ffprobe(video_path)
    audio_duration = _get_duration_ffprobe(audio_path)
    loops_needed = math.ceil(audio_duration / video_duration)
    
    print(f"DEBUG: Video Duration: {video_duration}")
    print(f"DEBUG: Audio Duration: {audio_duration}")
    print(f"DEBUG: Loops Needed: {loops_needed}")
    
    try:
        # Removido -shortest para que el video tenga la duración COMPLETA del audio
        # Usar -t con la duración exacta del audio para cortar el video sobrante del último loop
        cmd = ['ffmpeg', '-stream_loop', str(loops_needed), '-i', video_path, '-i', audio_path, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'copy', '-t', str(audio_duration), '-y', output_path]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"ADVERTENCIA: El método de loop rápido falló, usando método de fallback más confiable. Error: {e.stderr[:200]}")
        return _ffmpeg_loop_with_concat_demuxer(video_path, audio_path, output_path, loops_needed)

def _ffmpeg_loop_with_concat_demuxer(video_path, audio_path, output_path, loops):
    temp_dir = Path(OUTPUT_DIR) / "temp_ffmpeg"
    temp_dir.mkdir(parents=True, exist_ok=True)
    loop_list_path = temp_dir / f"loop_list_{os.getpid()}.txt"
    video_looped_path = temp_dir / f"video_looped_{os.getpid()}.mp4"
    with open(loop_list_path, 'w') as f:
        for _ in range(loops):
            f.write(f"file '{os.path.abspath(video_path)}'\n")
    try:
        cmd_loop = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', str(loop_list_path), '-c', 'copy', '-y', str(video_looped_path)]
        subprocess.run(cmd_loop, check=True, capture_output=True, text=True)
        # Removido -shortest para que el video tenga la duración COMPLETA del audio
        # Usar -t con la duración exacta del audio para cortar el video sobrante
        cmd_merge = ['ffmpeg', '-i', str(video_looped_path), '-i', audio_path, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'copy', '-t', str(audio_duration), '-y', output_path]
        subprocess.run(cmd_merge, check=True, capture_output=True, text=True)
        return output_path
    finally:
        if loop_list_path.exists(): loop_list_path.unlink()
        if video_looped_path.exists(): video_looped_path.unlink()

# --- Función Principal de Ensamblaje ---

def assemble_video(song_paths: list[str], lyrics_list: list[str], with_subtitles: bool = True, task_instance: Task = None) -> str:
    # --- Modificación para Robustez ---
    # Se ignora la lista de 'song_paths' de entrada y se escanea el directorio directamente
    # para asegurar que SIEMPRE se usen todos los archivos de audio existentes.
    
    def natural_sort_key(s):
        import re
        def atoi(text):
            return int(text) if text.isdigit() else text.lower()
        return [atoi(c) for c in re.split(r'(\d+)', s)]

    from src.config import SONGS_DIR
    all_song_files = [os.path.join(SONGS_DIR, f) for f in os.listdir(SONGS_DIR) if f.lower().endswith(('.mp3', '.wav', '.aac'))]
    if not all_song_files:
        raise FileNotFoundError(f"No se encontraron archivos de audio en el directorio '{SONGS_DIR}'.")
    
    # Usar la lista de archivos escaneada y ordenada a partir de ahora
    final_song_paths = sorted(all_song_files, key=natural_sort_key)
    
    print("\n=== ARCHIVOS DE AUDIO FINALES PARA EL VIDEO (Escaneo Directo) ===")
    for idx, path in enumerate(final_song_paths, 1):
        print(f"{idx}. {os.path.basename(path)}")
    print("===============================================================\n")
    # --- Fin de la Modificación ---

    subtitle_cache, moviepy_clips, temp_files = {}, [], []
    def update_status(details: str): print(details)
    try:
        update_status("🚀 Iniciando ensamblaje híbrido...")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        temp_dir = Path(OUTPUT_DIR) / "temp_ffmpeg"
        temp_dir.mkdir(parents=True, exist_ok=True)

        video_files = sorted([os.path.join(CLIPS_DIR, f) for f in os.listdir(CLIPS_DIR) if f.lower().endswith(('.mp4', '.mov', '.m4v'))])
        if not video_files: raise FileNotFoundError(f"No se encontraron videos en '{CLIPS_DIR}'.")

        video_concat_path = temp_dir / f"video_concat_{os.getpid()}.mp4"
        audio_concat_path = temp_dir / f"audio_concat_{os.getpid()}.mp3"
        temp_files.extend([video_concat_path, audio_concat_path])

        _ffmpeg_concatenate_files(video_files, video_concat_path, 'video')
        _ffmpeg_concatenate_files(final_song_paths, audio_concat_path, 'audio') # Usar final_song_paths

        video_looped_path = temp_dir / f"video_looped_{os.getpid()}.mp4"
        temp_files.append(video_looped_path)
        _ffmpeg_loop_video_smart(video_concat_path, audio_concat_path, video_looped_path)

        if not with_subtitles or not lyrics_list:
            # Sin subtítulos o sin letras disponibles: copiar directamente el video con audio completo
            import shutil
            update_status("📝 Generando video sin subtítulos...")
            shutil.copy(video_looped_path, VIDEO_OUTPUT_PATH)
        else:
            # Con subtítulos: expandir letras si es necesario y generar subtítulos
            update_status("📝 Preparando subtítulos...")
            
            # Expandir letras automáticamente si hay discrepancia
            if len(lyrics_list) != len(final_song_paths):
                print(f"⚠️ Discrepancia en video_assembler: {len(lyrics_list)} letras vs {len(final_song_paths)} canciones")
                if len(lyrics_list) > 0:
                    # Expandir letras de forma cíclica para cubrir todas las canciones
                    num_songs = len(final_song_paths)
                    num_lyrics = len(lyrics_list)
                    
                    expanded_lyrics = []
                    for i in range(num_songs):
                        # Usar módulo para ciclar a través de las letras disponibles
                        lyric_index = i % num_lyrics
                        expanded_lyrics.append(lyrics_list[lyric_index])
                    
                    lyrics_list = expanded_lyrics
                    print(f"✅ Letras expandidas automáticamente a {len(lyrics_list)} elementos (cíclicamente)")
                else:
                    print(f"⚠️ No hay letras disponibles, generando video sin subtítulos")
                    import shutil
                    shutil.copy(video_looped_path, VIDEO_OUTPUT_PATH)
                    update_status(f"✅ ¡Video generado exitosamente! Guardado en: {VIDEO_OUTPUT_PATH}")
                    return VIDEO_OUTPUT_PATH
            
            font_path = get_system_font_path()
            if not font_path: raise RuntimeError("No se encontró una fuente de sistema para los subtítulos.")
            final_video_base = VideoFileClip(str(video_looped_path))
            moviepy_clips.append(final_video_base)
            
            audio_durations = [_get_duration_ffprobe(sp) for sp in final_song_paths] # Usar final_song_paths
            audio_start_time = 0
            subtitle_clips = []

            for i, (lyrics, song_duration) in enumerate(zip(lyrics_list, audio_durations)):
                lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
                if not lines: continue
                time_per_line = song_duration / len(lines)
                for j, line in enumerate(lines):
                    if line not in subtitle_cache:
                        subtitle_cache[line] = TextClip(font=font_path, text=line, font_size=PERFORMANCE_CONFIG['subtitle_font_size'], color='white', stroke_color='black', stroke_width=PERFORMANCE_CONFIG['subtitle_stroke_width'], method=PERFORMANCE_CONFIG['subtitle_method'])
                    txt_clip = subtitle_cache[line].with_position(('center', 'bottom')).with_start(audio_start_time + j * time_per_line).with_duration(time_per_line)
                    fade_duration = min(PERFORMANCE_CONFIG['subtitle_fade_duration'], time_per_line / 3)
                    subtitle_clips.append(txt_clip.with_effects([vfx.CrossFadeIn(fade_duration), vfx.CrossFadeOut(fade_duration)]))
                audio_start_time += song_duration
            
            moviepy_clips.extend(subtitle_clips)
            final_composition = CompositeVideoClip([final_video_base] + subtitle_clips)
            final_composition.audio = final_video_base.audio
            moviepy_clips.append(final_composition)
            final_composition.write_videofile(VIDEO_OUTPUT_PATH, codec=PERFORMANCE_CONFIG['codec'], audio_codec=PERFORMANCE_CONFIG['audio_codec'], bitrate=PERFORMANCE_CONFIG['bitrate'], audio_bitrate=PERFORMANCE_CONFIG['audio_bitrate'], fps=PERFORMANCE_CONFIG['fps'], threads=PERFORMANCE_CONFIG['threads'], logger='bar')
        
        update_status(f"✅ ¡Video generado exitosamente! Guardado en: {VIDEO_OUTPUT_PATH}")
        return VIDEO_OUTPUT_PATH
    except Exception as e:
        update_status(f"❌ Error durante el ensamblaje: {e}")
        raise
    finally:
        update_status("🧹 Limpiando recursos...")
        for clip in moviepy_clips + list(subtitle_cache.values()):
            try: clip.close()
            except: pass
        if PERFORMANCE_CONFIG['cleanup_temp_files']:
            for temp_file in temp_files:
                if temp_file.exists():
                    try: temp_file.unlink()
                    except: pass