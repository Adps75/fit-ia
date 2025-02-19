from flask import Flask, request, jsonify
import requests
import os
import json
import re

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 🔹 Configuration OpenAI et Bubble
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante !")
if not BUBBLE_API_KEY:
    raise ValueError("❌ Clé API Bubble manquante !")

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Fonction pour envoyer les données à Bubble
# ─────────────────────────────────────────────────────────────────────────────

def send_to_bubble(endpoint, payload):
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"➡️ Envoi à Bubble : {url}\n📦 Payload : {json.dumps(payload, indent=2)}")
    print(f"🔄 Réponse API Bubble : {response.status_code} | {response.text}")
    
    return response.json() if response.status_code == 200 else None

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Nettoyage JSON OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def clean_json_response(response_text: str) -> str:
    cleaned_text = re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Génération du programme avec OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def generate_training_program(data):
    prompt = f"""
    Génère un programme structuré EN JSON STRICT.
    Paramètres :
    - Sport : {data["sport"]}
    - Niveau : {data["level"]}
    - Fréquence : {data["frequency"]} fois/semaine
    - Objectif : {data["goal"]}
    - Genre : {data["genre"]}
    """

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Erreur OpenAI : {response.status_code} | {response.text}")
        return None
    
    response_json = response.json()
    content = response_json["choices"][0]["message"]["content"]
    return json.loads(clean_json_response(content))

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Envoi du programme généré à Bubble
# ─────────────────────────────────────────────────────────────────────────────

def process_training_program(data):
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Échec de la génération du programme"}

    programme_payload = {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_durée": programme_data["programme"]["durée"],
        "list_cycles": []
    }
    programme_response = send_to_bubble("create_programme", programme_payload)
    
    if not programme_response or "id" not in programme_response["response"]:
        return {"error": "ID programme manquant"}
    
    programme_id = programme_response["response"]["id"]
    
    for cycle in programme_data["programme"].get("list_cycles", []):
        cycle_payload = {"programme_id": programme_id, "cycle_nom": cycle["nom"], "cycle_durée": cycle["durée"], "list_semaines": []}
        cycle_response = send_to_bubble("create_cycle", cycle_payload)
        
        if not cycle_response or "id" not in cycle_response["response"]:
            continue
        
        cycle_id = cycle_response["response"]["id"]
        programme_payload["list_cycles"].append(cycle_id)

        for semaine in cycle.get("list_semaines", []):
            semaine_payload = {"cycle_id": cycle_id, "semaine_numero": semaine["numéro"], "list_séances": []}
            semaine_response = send_to_bubble("create_semaine", semaine_payload)
            
            if not semaine_response or "id" not in semaine_response["response"]:
                continue
            
            semaine_id = semaine_response["response"]["id"]
            cycle_payload["list_semaines"].append(semaine_id)

            for seance in semaine.get("list_séances", []):
                seance_payload = {"semaine_id": semaine_id, "seance_nom": seance["nom"], "seance_numero": seance["numéro"], "list_exercices": []}
                seance_response = send_to_bubble("create_seance", seance_payload)
                
                if not seance_response or "id" not in seance_response["response"]:
                    continue
                
                seance_id = seance_response["response"]["id"]
                semaine_payload["list_séances"].append(seance_id)

                for exercice in seance.get("list_exercices", []):
                    exercice_payload = {"seance_id": seance_id, "exercice_nom": exercice["nom"], "exercice_temps_repos": exercice["temps_de_repos"], "list_séries": []}
                    exercice_response = send_to_bubble("create_exercice", exercice_payload)
                    
                    if not exercice_response or "id" not in exercice_response["response"]:
                        continue
                    
                    exercice_id = exercice_response["response"]["id"]
                    seance_payload["list_exercices"].append(exercice_id)

                    for serie in exercice.get("list_séries", []):
                        send_to_bubble("create_serie", {"exercice_id": exercice_id, "serie_charge": serie["charge"], "serie_repetitions": serie["répétitions"], "serie_nombre": serie["séries"]})
    
    return {"message": "Programme enregistré avec succès !"}

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
