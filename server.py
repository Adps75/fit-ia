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
    cleaned_text = re.sub(r"```json\\s*(.*?)\\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Génération du programme d'entraînement avec OpenAI (Gestion d'erreur améliorée)
# ─────────────────────────────────────────────────────────────────────────────

def generate_training_program(data):
    """
    Génère un programme structuré via OpenAI, en JSON strict.
    """
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE, sans commentaire ni texte hors du JSON.
    Paramètres :
    - Sport : {data["sport"]}
    - Niveau : {data["level"]}
    - Fréquence : {data["frequency"]} fois par semaine
    - Objectif : {data["goal"]}
    - Genre : {data["genre"]}
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
        
        if "choices" not in response_json or not response_json["choices"]:
            print("❌ OpenAI a renvoyé une réponse vide.")
            return None

        message_content = response_json["choices"][0]["message"]["content"]
        if not message_content:
            print("❌ OpenAI a renvoyé un message vide.")
            return None

        cleaned_json = clean_json_response(message_content)
        
        if not cleaned_json:
            print("❌ JSON nettoyé est vide, vérifiez la réponse d'OpenAI.")
            return None
        
        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        print(f"❌ Erreur JSON : {str(e)}")
        print(f"🔍 Réponse brute OpenAI après nettoyage : {cleaned_json}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Endpoint Flask pour gérer la génération du programme
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = generate_training_program(data)
    
    if result is None:
        return jsonify({"error": "Échec de la génération du programme"}), 500
    
    return jsonify(result), 201

# ─────────────────────────────────────────────────────────────────────────────
# 📌 Démarrage de l’application Flask
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
