from flask import Flask, request, jsonify
import requests
import os
import json
import re

app = Flask(__name__)

# Configuration OpenAI et Bubble
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

def send_to_bubble(endpoint, payload):
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json() if response.status_code == 200 else None

def update_parent_list(endpoint, parent_id, field_name, child_id):
    """
    Met à jour un parent avec la liste des enfants associés.
    """
    payload = {"id": parent_id, field_name: [child_id]}
    return send_to_bubble(endpoint, payload)

def clean_json_response(response_text: str) -> str:
    """
    Supprime les balises Markdown (```json ... ```) mais conserve le JSON intact.
    """
    match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()

def generate_training_program(data):
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE.
    Paramètres :
    - Sport : {data.get("sport", "")}
    - Niveau : {data.get("level", "")}
    - Fréquence : {data.get("frequency", "")} fois par semaine
    - Objectif : {data.get("goal", "")}
    - Genre : {data.get("genre", "")}
    """
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ OpenAI Error {response.status_code}: {response.text}")
        return None
    
    try:
        response_json = response.json()
        message_content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        if not message_content:
            print("❌ OpenAI a renvoyé une réponse vide.")
            return None
        
        print(f"🔄 Réponse OpenAI avant nettoyage : {message_content}")
        cleaned_json = clean_json_response(message_content)
        
        if not cleaned_json:
            print("❌ Le nettoyage a renvoyé une réponse vide.")
            return None
        
        print(f"✅ Réponse OpenAI après nettoyage : {cleaned_json}")
        return json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        print(f"❌ Erreur de décodage JSON: {str(e)}")
        print(f"🔍 Réponse brute OpenAI après nettoyage : {cleaned_json}")
        return None

def process_training_program(data):
    programme_data = generate_training_program(data)
    
    if not programme_data:
        return {"error": "Échec de la génération du programme"}
    
    if "programme" not in programme_data:
        print("❌ Erreur : La clé 'programme' est absente du JSON retourné.")
        print(f"🔍 JSON reçu : {programme_data}")
        return {"error": "Données du programme invalides"}
    
    programme = programme_data["programme"]
    programme_nom = programme.get("nom", "Programme sans nom")
    programme_duree = programme.get("durée", 0)
    
    programme_payload = {"programme_nom": programme_nom, "programme_durée": programme_duree}
    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]
    
    programme_response = send_to_bubble("create_programme", programme_payload)
    if not programme_response or "response" not in programme_response or "id" not in programme_response["response"]:
        return {"error": "ID programme manquant"}
    
    programme_id = programme_response["response"]["id"]
    
    for cycle in programme.get("list_cycles", []):
        cycle_payload = {"programme_id": programme_id, "cycle_nom": cycle.get("nom", "Cycle sans nom"), "cycle_durée": cycle.get("durée", 1)}
        cycle_response = send_to_bubble("create_cycle", cycle_payload)
        if not cycle_response or "response" not in cycle_response or "id" not in cycle_response["response"]:
            continue
        cycle_id = cycle_response["response"]["id"]
        update_parent_list("update_programme", programme_id, "list_cycles", cycle_id)
    
    return {"message": "Programme enregistré avec succès !"}

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
