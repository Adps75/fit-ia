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
    cleaned_text = re.sub(r"```json\\s*(.*?)\\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Génération du programme d'entraînement avec OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def generate_training_program(data):
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE, 
    sans commentaire ni texte hors du JSON.
    
    Exemple minimal :

    ```json
    {{
      "programme": {{
        "nom": "{data.get('programme_nom', 'Programme personnalisé')}",
        "durée": {data.get('programme_duree', 12)},
        "list_cycles": [
          {{
            "nom": "Cycle 1",
            "durée": 3,
            "list_semaines": [
              {{
                "numéro": 1,
                "list_séances": [
                  {{
                    "numéro": 1,
                    "list_exercices": [
                      {{
                        "nom": "Développé couché",
                        "temps_de_repos": 60,
                        "list_séries": [
                          {{ "charge": 40, "répétitions": 10, "séries": 3 }}
                        ]
                      }}
                    ]
                  }}
                ]
              }}
            ]
          }}
        ]
      }}
    }}
    ```
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
        cleaned_json = clean_json_response(response_json["choices"][0]["message"]["content"])
        return json.loads(cleaned_json)
    except json.JSONDecodeError:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Fonction principale pour traiter le programme et l'envoyer à Bubble
# ─────────────────────────────────────────────────────────────────────────────

def process_training_program(data):
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Échec de la génération du programme"}

    programme = programme_data["programme"]
    programme_response = send_to_bubble("create_programme", {
        "programme_nom": programme["nom"],
        "programme_durée": programme["durée"],
        "list_cycles": []  # Ajout des références des cycles
    })
    if not programme_response:
        return {"error": "Échec de la création du programme"}

    programme_id = programme_response["response"]["id"]
    for cycle in programme["list_cycles"]:
        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle["nom"],
            "cycle_durée": cycle["durée"],
            "list_semaines": []
        })
        if cycle_response:
            programme_response["response"]["list_cycles"].append(cycle_response["response"]["id"])
        
        cycle_id = cycle_response["response"]["id"]
        for semaine in cycle["list_semaines"]:
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine["numéro"],
                "list_séances": []
            })
            if semaine_response:
                cycle_response["response"]["list_semaines"].append(semaine_response["response"]["id"])
            
            semaine_id = semaine_response["response"]["id"]
            for seance in semaine["list_séances"]:
                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance["numéro"],
                    "list_exercices": []
                })
                if seance_response:
                    semaine_response["response"]["list_séances"].append(seance_response["response"]["id"])

    return {"message": "Programme enregistré avec succès !"}

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
