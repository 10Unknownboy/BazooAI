import json

with open('notebooks/ai_dj_colab_server.ipynb', 'r', encoding='utf-8') as f:
    data = json.load(f)

for cell in data['cells']:
    if 'source' in cell:
        for i, line in enumerate(cell['source']):
            if 'HF_MODEL_NAME = "google/gemma-2-2b-it"' in line:
                cell['source'][i] = line.replace('google/gemma-2-2b-it', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0')
            if 'PROJECT_DIR = REPO_DIR' in line:
                cell['source'][i] = 'PROJECT_DIR = f"{REPO_DIR}/ai_dj_system"\n'

with open('notebooks/ai_dj_colab_server.ipynb', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
