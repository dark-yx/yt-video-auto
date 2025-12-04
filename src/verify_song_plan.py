
import sys
import os

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lyric_generator import generate_song_plan

def test_song_plan():
    prompt = "Un álbum conceptual sobre un viaje interestelar en busca de un nuevo hogar"
    language = "spanish"
    total_songs = 3
    
    print(f"Testing generate_song_plan with prompt: '{prompt}'")
    print("-" * 50)
    
    try:
        result = generate_song_plan(prompt, total_songs, language)
        print("Result:")
        print(result)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_song_plan()
