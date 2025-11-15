import re

def parse_lyrics_file(file_content: str) -> dict:
    """
    Parses the content of a lyric file to extract title, prompt, tags, and gender
    in a more robust way using splits.
    """
    parsed_data = {
        'title': 'Untitled Song',
        'prompt': '',
        'tags': '',
        'gender': 'female'  # Default gender
    }

    try:
        # Use regex split to handle case-insensitivity and potential surrounding whitespace/newlines
        # The pattern looks for the keyword at the beginning of a line.
        
        # --- Extract TITLE from the header part ---
        header_parts = re.split(r'^\s*PROMPT:', file_content, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)
        header = header_parts[0]
        
        title_match = re.search(r'TITLE:(.*)', header, flags=re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip().strip("'\"")
            if title:
                parsed_data['title'] = title

        # --- Extract PROMPT, TAGS, and GENERO from the rest of the body ---
        if len(header_parts) > 1:
            body = header_parts[1]
            
            # Split body by TAGS
            prompt_parts = re.split(r'^\s*TAGS:', body, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)
            prompt_content = prompt_parts[0].strip()
            if prompt_content:
                parsed_data['prompt'] = prompt_content
            
            if len(prompt_parts) > 1:
                tags_body = prompt_parts[1]
                
                # Split tags part by GENERO
                tags_parts = re.split(r'^\s*GENERO:', tags_body, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)
                tags_content = tags_parts[0].strip()
                if tags_content:
                    parsed_data['tags'] = tags_content
                
                if len(tags_parts) > 1:
                    genero_content = tags_parts[1].strip().lower()
                    if 'femenino' in genero_content:
                        parsed_data['gender'] = 'female'
                    elif 'masculino' in genero_content:
                        parsed_data['gender'] = 'male'

    except Exception as e:
        print(f"Error parsing lyrics file with new logic: {e}. The generated .txt file might have a format issue.")
        # If the new logic fails, we can add a fallback to a simpler method or just return defaults.
        # For now, we let it return the defaults for the fields it couldn't parse.
        pass

    return parsed_data
