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
    return re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL).strip()

def generate_training_program(data):
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE.
    Paramètres :
    - Sport : {data["sport"]}
    - Niveau : {data["level"]}
    - Fréquence : {data["frequency"]} fois par semaine
    - Objectif : {data["goal"]}
    - Genre : {data["genre"]}
    """
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    if response.status_code != 200:
        return None
    response_json = response.json()
    message_content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
    cleaned_json = clean_json_response(message_content)
    return json.loads(cleaned_json) if cleaned_json else None

def process_training_program(data):
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Échec de la génération du programme"}
    programme_payload = {"programme_nom": programme_data["programme"]["nom"], "programme_durée": programme_data["programme"]["durée"]}
    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]
    programme_response = send_to_bubble("create_programme", programme_payload)
    if not programme_response or "response" not in programme_response or "id" not in programme_response["response"]:
        return {"error": "ID programme manquant"}
    programme_id = programme_response["response"]["id"]
    for cycle in programme_data["programme"]["list_cycles"]:
        cycle_payload = {"programme_id": programme_id, "cycle_nom": cycle.get("nom", "Cycle sans nom"), "cycle_durée": cycle.get("durée", 1)}
        cycle_response = send_to_bubble("create_cycle", cycle_payload)
        if not cycle_response or "response" not in cycle_response or "id" not in cycle_response["response"]:
            continue
        cycle_id = cycle_response["response"]["id"]
        update_parent_list("update_programme", programme_id, "list_cycles", cycle_id)
        for semaine in cycle["list_semaines"]:
            semaine_payload = {"cycle_id": cycle_id, "semaine_numero": semaine.get("numéro", 1)}
            semaine_response = send_to_bubble("create_semaine", semaine_payload)
            if not semaine_response or "response" not in semaine_response or "id" not in semaine_response["response"]:
                continue
            semaine_id = semaine_response["response"]["id"]
            update_parent_list("update_cycle", cycle_id, "list_semaines", semaine_id)
            for seance in semaine["list_séances"]:
                seance_payload = {"semaine_id": semaine_id, "seance_nom": seance.get("nom", "Séance"), "seance_numero": seance.get("numéro", 1)}
                seance_response = send_to_bubble("create_seance", seance_payload)
                if not seance_response or "response" not in seance_response or "id" not in seance_response["response"]:
                    continue
                seance_id = seance_response["response"]["id"]
                update_parent_list("update_semaine", semaine_id, "list_seances", seance_id)
                for exercice in seance["list_exercices"]:
                    exercice_payload = {"seance_id": seance_id, "exercice_nom": exercice.get("nom", "Exercice"), "exercice_temps_repos": exercice.get("temps_de_repos", 60)}
                    exercice_response = send_to_bubble("create_exercice", exercice_payload)
                    if not exercice_response or "response" not in exercice_response or "id" not in exercice_response["response"]:
                        continue
                    exercice_id = exercice_response["response"]["id"]
                    update_parent_list("update_seance", seance_id, "list_exercices", exercice_id)
                    for serie in exercice["list_séries"]:
                        for i in range(serie.get("séries", 1)):
                            serie_payload = {
                                "exercice_id": exercice_id,
                                "serie_charge": serie.get("charge", 0),
                                "serie_repetitions": serie.get("répétitions", 0),
                                "serie_index": i + 1
                            }
                            serie_response = send_to_bubble("create_serie", serie_payload)
                            if serie_response and "response" in serie_response and "id" in serie_response["response"]:
                                serie_id = serie_response["response"]["id"]
                                update_parent_list("update_exercice", exercice_id, "list_series", serie_id)
    return {"message": "Programme enregistré avec succès !"}

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
