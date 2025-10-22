
import requests
import uuid
import time
import os
import re
from src.config import SUNO_COOKIE

class SunoApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.device_id = str(uuid.uuid4())
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0",
            "device-id": self.device_id
        })
        self._set_cookies_from_string(SUNO_COOKIE)
        self.auth_token = None
        self.session_id = None
        self.clerk_base_url = "https://clerk.suno.com/v1"
        self.api_base_url = "https://studio-api.prod.suno.com/api"

    def _set_cookies_from_string(self, cookie_string):
        if not cookie_string:
            return
        for cookie in cookie_string.split(';'):
            cookie = cookie.strip()
            if not cookie:
                continue
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                self.session.cookies.set(name, value)
            else:
                self.session.cookies.set(cookie, None)

    def _get_session_token(self):
        response = self.session.get(f"{self.clerk_base_url}/client?__clerk_api_version=2025-04-10&_clerk_js_version=5.102.0")
        response.raise_for_status()
        data = response.json()
        jwt_token = data.get("response", {}).get("sessions", [{}])[0].get("last_active_token", {}).get("jwt")
        if not jwt_token:
            raise Exception("Could not retrieve JWT token from Clerk.")
        self.auth_token = jwt_token
        self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
        return jwt_token

    def check_connection(self):
        if not self.auth_token:
            self._get_session_token()
        response = self.session.get(f"{self.api_base_url}/user/get_user_session_id/")
        response.raise_for_status()
        return response.json()

    def generate(self, tags, title, prompt, make_instrumental, vocal_gender='f', mv="chirp-crow"):
        if not self.auth_token:
            self._get_session_token()
        
        project_id = "3416bdd1-11da-4e80-b781-7c689f2260e1"

        # Build a single, consistent payload structure based on the "custom" mode
        payload = {
            "project_id": project_id,
            "generation_type": "TEXT",
            "mv": mv,
            "prompt": prompt,
            "tags": tags,
            "title": title,
            "make_instrumental": make_instrumental,
            "metadata": {
                "create_mode": "custom",
                "stream": True,
                "priority": 10,
                "control_sliders": {
                    "style_weight": 0.5,
                    "weirdness_constraint": 0.5
                },
            }
        }

        # Only add vocal_gender if it's not an instrumental
        if not make_instrumental:
            payload["metadata"]["vocal_gender"] = vocal_gender
        
        response = self.session.post(f"{self.api_base_url}/generate/v2-web/", json=payload)
        
        if not response.ok:
            error_details = f"Status Code: {response.status_code}"
            try:
                error_json = response.json()
                error_details += f" - Body: {error_json}"
            except ValueError:
                error_details += f" - Body: {response.text}"
            raise Exception(f"Suno API Error: {error_details}")
            
        return response.json()

    def poll_for_song(self, ids):
        if not self.auth_token:
            self._get_session_token()
        if isinstance(ids, str):
            ids = [ids]
        endpoint = f"{self.api_base_url}/feed/v2?ids={','.join(ids)}"
        while True:
            response = self.session.get(endpoint)
            response.raise_for_status()
            data = response.json()

            # The response is a dict containing a 'clips' list.
            clips = data.get('clips', [])

            # Check if clips is a list and if all songs in it are complete
            if clips and isinstance(clips, list) and all(isinstance(song, dict) and song.get('status') == 'complete' for song in clips):
                return clips # Return the list of completed clips

            print("Song not ready, polling again in 10 seconds...")
            time.sleep(10)

    def download_song(self, song_id, song_title, output_filename=None):
        if not self.auth_token:
            self._get_session_token()
        
        # Get the download URL
        response = self.session.post(f"{self.api_base_url}/billing/clips/{song_id}/download/")
        response.raise_for_status()
        download_url = response.json().get("url")

        if not download_url:
            raise Exception("Could not retrieve download URL.")

        # Download the song content
        audio_response = requests.get(download_url, stream=True)
        audio_response.raise_for_status()

        if output_filename:
            # Use the provided filename
            file_path = os.path.join("songs", output_filename)
        else:
            # Sanitize title to create a filename if not provided
            safe_title = re.sub(r'[\\/*?"<>|]', "", song_title)
            file_path = os.path.join("songs", f"{safe_title}.mp3")

        # Save the song
        with open(file_path, 'wb') as f:
            for chunk in audio_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded '{song_title}' to {file_path}")
        return file_path

if __name__ == "__main__":
    client = SunoApiClient()
    try:
        prompt = """A song about the joy of coding and creating new things."""
        tags = "upbeat, electronic, pop"
        title = "Code Creations"

        generation_response = client.generate(prompt, tags, title)
        print("Successfully submitted generation task.")
        
        song_ids = [clip['id'] for clip in generation_response['clips']]
        print(f"Polling for songs with IDs: {song_ids}")

        final_songs = client.poll_for_song(song_ids)

        print("\n--- Generation Complete! ---")
        for song in final_songs:
            print(f"Title: {song['title']}")
            print(f"Audio URL: {song['audio_url']}")
            client.download_song(song['id'], song['title'])
            print("---")

    except Exception as e:
        print(f"An error occurred: {e}")
