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
# 📌 Fonction principale pour traiter le programme et l'envoyer à Bubble
# ─────────────────────────────────────────────────────────────────────────────

def process_training_program(data):
    """
    Génère un programme via OpenAI et l'envoie à Bubble
    """
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

    if not programme_response or "response" not in programme_response or "id" not in programme_response["response"]:
        return {"error": "ID programme manquant"}

    programme_id = programme_response["response"]["id"]

    for cycle in programme_data["programme"].get("list_cycles", []):
        cycle_payload = {
            "programme_id": programme_id,
            "cycle_nom": cycle.get("nom", "Cycle sans nom"),
            "cycle_durée": cycle.get("durée", 1)
        }
        cycle_response = send_to_bubble("create_cycle", cycle_payload)
        if not cycle_response or "response" not in cycle_response or "id" not in cycle_response["response"]:
            continue

        cycle_id = cycle_response["response"]["id"]

        for semaine in cycle.get("list_semaines", []):
            semaine_payload = {
                "cycle_id": cycle_id,
                "semaine_numero": semaine.get("numéro", 1),
                "programme_id": programme_id
            }
            semaine_response = send_to_bubble("create_semaine", semaine_payload)
            if not semaine_response or "response" not in semaine_response or "id" not in semaine_response["response"]:
                continue

            semaine_id = semaine_response["response"]["id"]

            for seance in semaine.get("list_séances", []):
                seance_payload = {
                    "semaine_id": semaine_id,
                    "seance_nom": seance.get("nom", f"Semaine {semaine.get('numéro', 1)} - Séance"),
                    "seance_numero": seance.get("numéro", 1),
                    "programme_id": programme_id
                }
                seance_response = send_to_bubble("create_seance", seance_payload)
                if not seance_response or "response" not in seance_response or "id" not in seance_response["response"]:
                    continue

                seance_id = seance_response["response"]["id"]

                for exercice in seance.get("list_exercices", []):
                    exercice_payload = {
                        "seance_id": seance_id,
                        "exercice_nom": exercice.get("nom", "Exercice"),
                        "exercice_temps_repos": exercice.get("temps_de_repos", 60),
                        "programme_id": programme_id
                    }
                    exercice_response = send_to_bubble("create_exercice", exercice_payload)
                    if not exercice_response or "response" not in exercice_response or "id" not in exercice_response["response"]:
                        continue

                    exercice_id = exercice_response["response"]["id"]

                    for serie in exercice.get("list_séries", []):
                        serie_payload = {
                            "exercice_id": exercice_id,
                            "serie_charge": serie.get("charge", 0),
                            "serie_repetitions": serie.get("répétitions", 0),
                            "serie_nombre": serie.get("séries", 1),
                            "programme_id": programme_id
                        }
                        send_to_bubble("create_serie", serie_payload)

    return {"message": "Programme enregistré avec succès !"}


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Endpoint Flask pour gérer la génération du programme
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Démarrage de l’application Flask
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
