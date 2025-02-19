from flask import Flask, request, jsonify
import requests
import os
import json
import re  # Pour nettoyer les balises Markdown

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 🔹 Configuration OpenAI et Bubble
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

# Vérification des clés
if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")
if not BUBBLE_API_KEY:
    raise ValueError("❌ Clé API Bubble manquante ! Ajoutez-la dans les variables d'environnement.")


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Fonction pour envoyer les données à Bubble Backend Workflows
# ─────────────────────────────────────────────────────────────────────────────

def send_to_bubble(endpoint, payload):
    """
    Envoie les données à Bubble avec le header Authorization
    et retourne le JSON de la réponse si status=200.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Fonction pour nettoyer la réponse JSON d'OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def clean_json_response(response_text: str) -> str:
    """
    Supprime les balises Markdown (```json ... ```).
    On ne garde que le contenu JSON brut.
    """
    cleaned_text = re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Génération du programme d'entraînement avec OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def generate_training_program(data):
    """
    Génère un programme structuré via OpenAI, en JSON strict.
    """
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE, 
    sans commentaire ni texte hors du JSON.

    Chaque séance possède une liste d'exercices,
    chaque exercice a une liste de séries.
    """

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"❌ Erreur OpenAI : {response.status_code} | {response.text}")
        return None

    try:
        response_json = response.json()
        print(f"🔄 Réponse OpenAI : {json.dumps(response_json, indent=2)}")

        message_content = response_json["choices"][0]["message"]["content"]
        cleaned_json = clean_json_response(message_content)
        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        print(f"❌ Erreur JSON : {str(e)}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Traitement du programme et envoi à Bubble
# ─────────────────────────────────────────────────────────────────────────────

def process_training_program(data):
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Échec de la génération du programme"}

    programme_payload = {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_durée": programme_data["programme"]["durée"]
    }

    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]

    programme_response = send_to_bubble("create_programme", programme_payload)
    if not programme_response or "response" not in programme_response:
        return {"error": "ID programme manquant"}
    programme_id = programme_response["response"]["id"]

    for cycle in programme_data["programme"].get("list_cycles", []):
        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle["nom"],
            "cycle_durée": cycle["durée"]
        })
        if not cycle_response:
            continue
        cycle_id = cycle_response["response"]["id"]

        for semaine in cycle.get("list_semaines", []):
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine["numéro"]
            })
            if not semaine_response:
                continue
            semaine_id = semaine_response["response"]["id"]

            for seance in semaine.get("list_séances", []):
                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance["nom"],
                    "seance_numero": seance["numéro"]
                })
                if not seance_response:
                    continue
                seance_id = seance_response["response"]["id"]

                for exercice in seance.get("list_exercices", []):
                    exercice_response = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "exercice_nom": exercice["nom"],
                        "exercice_temps_repos": exercice.get("temps_de_repos", 60)
                    })
                    if not exercice_response:
                        continue
                    exercice_id = exercice_response["response"]["id"]

                    for serie in exercice.get("list_séries", []):
                        send_to_bubble("create_serie", {
                            "exercice_id": exercice_id,
                            "serie_charge": serie["charge"],
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
