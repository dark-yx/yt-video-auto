
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from unittest.mock import MagicMock, patch
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips
from moviepy.audio.AudioClip import concatenate_audioclips
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip


# Mock the config before other imports
from src import config
config.CLIPS_DIR = "tests/temp/clips"
config.VIDEO_OUTPUT_PATH = "tests/temp/output/final_video.mp4"
config.OUTPUT_DIR = "tests/temp/output"

from src.video_assembler import assemble_video

@pytest.fixture(scope="module")
def setup_test_environment():
    """Set up a temporary environment for tests."""
    # Create directories
    os.makedirs(config.CLIPS_DIR, exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs("tests/temp/songs", exist_ok=True)

    # Create dummy files
    dummy_clip_path = os.path.join(config.CLIPS_DIR, "clip1.mp4")
    dummy_song_path = "tests/temp/songs/song1.mp3"

    # Use moviepy to create silent video and audio files
    from moviepy import ColorClip, AudioArrayClip
    import numpy as np

    # Create a 1-second black video clip
    clip = ColorClip(size=(100, 100), color=(0, 0, 0), duration=1)
    clip.write_videofile(dummy_clip_path, codec="libx264", fps=24)

    # Create a 1-second silent audio clip
    audio = AudioArrayClip(np.zeros((44100, 2)), fps=44100)
    audio.write_audiofile(dummy_song_path)


    yield {
        "song_paths": [dummy_song_path],
        "lyrics_list": ["Hello\nWorld"],
    }

    # Teardown: Clean up the created files and directories
    if os.path.exists(dummy_clip_path):
        os.remove(dummy_clip_path)
    if os.path.exists(dummy_song_path):
        os.remove(dummy_song_path)
    if os.path.exists(config.VIDEO_OUTPUT_PATH):
        os.remove(config.VIDEO_OUTPUT_PATH)
    
    os.rmdir(config.CLIPS_DIR)
    os.rmdir(config.OUTPUT_DIR)
    os.rmdir("tests/temp/songs")
    os.rmdir("tests/temp")


def test_assemble_video_creates_output(setup_test_environment):
    """
    Test that assemble_video successfully creates a video file.
    """
    # Get the test data from the fixture
    test_data = setup_test_environment

    # Mock the Celery task instance
    mock_task = MagicMock()
    mock_task.info = {}

    # Run the function
    output_path = assemble_video(
        song_paths=test_data["song_paths"],
        lyrics_list=test_data["lyrics_list"],
        task_instance=mock_task,
        with_subtitles=True,
    )

    # Assertions
    assert output_path == config.VIDEO_OUTPUT_PATH
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0

    # Verify that the progress was updated
    mock_task.update_state.assert_called()

