from flask import Flask, request, jsonify
import requests
import os
import json
import re  # Pour nettoyer les balises Markdown

app = Flask(__name__)

# Configuration OpenAI et Bubble
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")
if not BUBBLE_API_KEY:
    raise ValueError("❌ Clé API Bubble manquante ! Ajoutez-la dans les variables d'environnement.")

# Fonction pour envoyer les données à Bubble
def send_to_bubble(endpoint, payload):
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    response = requests.post(url, json=payload, headers=headers)
    print(f"➡️ Envoi à Bubble : {url}\n📦 Payload : {json.dumps(payload, indent=2)}")
    print(f"🔄 Réponse API Bubble : {response.status_code} | {response.text}")
    if response.status_code == 200:
        return response.json()
    else:
        return None

# Fonction pour nettoyer la réponse JSON d'OpenAI
def clean_json_response(response_text):
    return re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL).strip()

# Génération du programme d'entraînement avec OpenAI
def generate_training_program(data):
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE, sans commentaire ni texte hors du JSON.
    N'inclus pas d'expressions non numériques dans des champs numériques.
    Paramètres à prendre en compte :
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
    try:
        response_json = response.json()
        message_content = response_json["choices"][0]["message"]["content"]
        return json.loads(clean_json_response(message_content))
    except json.JSONDecodeError:
        return None

# Fonction pour traiter le programme et l'envoyer à Bubble
def process_training_program(data):
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Échec de la génération du programme"}
    programme_payload = {"programme_nom": programme_data["programme"]["nom"], "programme_durée": programme_data["programme"]["durée"]}
    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]
    programme_response = send_to_bubble("create_programme", programme_payload)
    if not programme_response or "id" not in programme_response.get("response", {}):
        return {"error": "ID programme manquant"}
    programme_id = programme_response["response"]["id"]
    
    list_cycles = []  # Ajout des cycles dans la liste du programme
    for cycle in programme_data["programme"].get("list_cycles", []):
        cycle_payload = {"programme_id": programme_id, "cycle_nom": cycle["nom"], "cycle_durée": cycle["durée"]}
        cycle_response = send_to_bubble("create_cycle", cycle_payload)
        if not cycle_response or "id" not in cycle_response.get("response", {}):
            continue
        cycle_id = cycle_response["response"]["id"]
        list_cycles.append(cycle_id)
        
        list_semaines = []  # Ajout des semaines dans le cycle
        for semaine in cycle.get("list_semaines", []):
            semaine_payload = {"cycle_id": cycle_id, "semaine_numero": semaine["numéro"]}
            semaine_response = send_to_bubble("create_semaine", semaine_payload)
            if not semaine_response or "id" not in semaine_response.get("response", {}):
                continue
            semaine_id = semaine_response["response"]["id"]
            list_semaines.append(semaine_id)
            
            list_seances = []  # Ajout des séances dans la semaine
            for seance in semaine.get("list_séances", []):
                seance_payload = {"semaine_id": semaine_id, "seance_nom": seance["numéro"], "seance_numero": seance["numéro"]}
                seance_response = send_to_bubble("create_seance", seance_payload)
                if not seance_response or "id" not in seance_response.get("response", {}):
                    continue
                seance_id = seance_response["response"]["id"]
                list_seances.append(seance_id)
                
                for exercice in seance.get("list_exercices", []):
                    exercice_payload = {"seance_id": seance_id, "exercice_nom": exercice["nom"], "exercice_temps_repos": exercice["temps_de_repos"]}
                    exercice_response = send_to_bubble("create_exercice", exercice_payload)
                    if not exercice_response or "id" not in exercice_response.get("response", {}):
                        continue
                    exercice_id = exercice_response["response"]["id"]
                    
                    for serie in exercice.get("list_séries", []):
                        send_to_bubble("create_serie", {
                            "exercice_id": exercice_id,
                            "serie_charge": str(serie["charge"]),  # Correction du type pour éviter l'erreur
                            "serie_repetitions": serie["répétitions"],
                            "serie_nombre": serie["séries"]
                        })
    return {"message": "Programme enregistré avec succès !"}

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
