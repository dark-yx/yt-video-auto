import re

def parse_lyrics_file(file_content: str) -> dict:
    """
    Parses the content of a lyric file to extract title, prompt, tags, and gender
    in a more robust way.
    """
    # --- Default values ---
    parsed_data = {
        'title': 'Untitled Song',
        'prompt': '',
        'tags': '',
        'gender': 'female'
    }

    # --- Extract TITLE ---
    title_match = re.search(r'TITLE:(.*)', file_content, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip().strip("'\"")
        if title:
            parsed_data['title'] = title

    # --- Find indices of all section headers ---
    def find_section_start(keyword, content):
        match = re.search(r'\n\s*' + keyword, content, re.IGNORECASE)
        return match.start() if match else -1

    prompt_start = find_section_start('PROMPT:', file_content)
    tags_start = find_section_start('TAGS:', file_content)
    genero_start = find_section_start('GENERO:', file_content)

    # --- Extract PROMPT ---
    if prompt_start != -1:
        end_of_prompt = len(file_content)
        if tags_start > prompt_start:
            end_of_prompt = tags_start
        elif genero_start > prompt_start:
            end_of_prompt = genero_start
        
        prompt_content_start = file_content.find('\n', prompt_start + 1)
        if prompt_content_start != -1:
            parsed_data['prompt'] = file_content[prompt_content_start:end_of_prompt].strip()

    # --- Extract TAGS ---
    if tags_start != -1:
        end_of_tags = len(file_content)
        if genero_start > tags_start:
            end_of_tags = genero_start

        tags_content_start = file_content.find('\n', tags_start + 1)
        if tags_content_start != -1:
            parsed_data['tags'] = file_content[tags_content_start:end_of_tags].strip()

    # --- Extract GENERO ---
    if genero_start != -1:
        # Find the start of the content for GENERO
        match = re.search(r'GENERO:(.*)', file_content, re.IGNORECASE | re.DOTALL)
        if match:
            gender_content = match.group(1).strip().lower()
            if 'femenino' in gender_content:
                parsed_data['gender'] = 'female'
            elif 'masculino' in gender_content:
                parsed_data['gender'] = 'male'
    
    return parsed_data
