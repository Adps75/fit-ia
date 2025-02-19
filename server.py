from flask import Flask, request, jsonify
import requests
import os
import json
import re  # Pour nettoyer les balises Markdown

app = Flask(__name__)

# 🔹 Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# 🔹 Configuration Bubble
BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

# 🔹 Vérification des clés API
if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")

if not BUBBLE_API_KEY:
    raise ValueError("❌ Clé API Bubble manquante ! Ajoutez-la dans les variables d'environnement.")

# 📌 Fonction pour envoyer les données à Bubble Backend Workflows
def send_to_bubble(endpoint, payload):
    """ Envoie les données à Bubble avec Authorization """
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

# 📌 Fonction pour nettoyer la réponse JSON d'OpenAI
def clean_json_response(response_text):
    """ Supprime les balises Markdown pour ne garder que le JSON brut """
    cleaned_text = re.sub(r"```json\n(.*?)\n```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()

# 📌 Génération du programme d'entraînement avec OpenAI
def generate_training_program(data):
    """ Génère un programme structuré via OpenAI """
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme structuré en JSON, sans texte additionnel.

    Paramètres :
    - Sport : {data["sport"]}
    - Niveau : {data["level"]}
    - Fréquence : {data["frequency"]} fois par semaine
    - Objectif : {data["goal"]}
    - Genre : {data["genre"]}

    JSON attendu :
    ```json
    {{
      "programme": {{
        "nom": "{data.get('programme_nom', 'Programme personnalisé')}",
        "durée": {data.get('programme_duree', 12)},
        "list_cycles": [...]
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
        print(f"🔄 Réponse OpenAI : {json.dumps(response_json, indent=2)}")

        if "choices" not in response_json or not response_json["choices"]:
            print("❌ OpenAI a renvoyé une réponse vide.")
            return None

        message_content = response_json["choices"][0]["message"]["content"]
        if not message_content:
            print("❌ OpenAI a renvoyé un message vide.")
            return None

        # 🔥 Nettoyage du JSON
        cleaned_json = clean_json_response(message_content)

        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        print(f"❌ Erreur JSON : {str(e)}")
        print(f"🔍 Réponse brute OpenAI après nettoyage : {cleaned_json}")
        return None

# 📌 Fonction principale pour traiter le programme et l'envoyer à Bubble
def process_training_program(data):
    """ Génère un programme et l'envoie aux API Workflows de Bubble """
    programme_data = generate_training_program(data)

    if not programme_data:
        return {"error": "Échec de la génération du programme"}

    # 1️⃣ Enregistrement du Programme
    programme_payload = {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_durée": programme_data["programme"]["durée"]
    }

    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]  # Ajoute l'ID de l'utilisateur

    programme_response = send_to_bubble("create_programme", programme_payload)

    if not programme_response or "id" not in programme_response:
        print(f"❌ Erreur : ID programme manquant dans la réponse Bubble {programme_response}")
        return {"error": "ID programme manquant"}

    programme_id = programme_response["id"]
    print(f"✅ Programme enregistré avec ID : {programme_id}")

    # 2️⃣ Enregistrement des Cycles
    for cycle in programme_data["programme"]["list_cycles"]:
        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle["nom"],
            "cycle_durée": cycle["durée"]
        })
        if not cycle_response:
            continue

        cycle_id = cycle_response.get("id")

        # 3️⃣ Enregistrement des Semaines
        for semaine in cycle["list_semaines"]:
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine["numéro"]
            })
            if not semaine_response:
                continue

            semaine_id = semaine_response.get("id")

            # 4️⃣ Enregistrement des Séances
            for seance in semaine["list_séances"]:
                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance["nom"],
                    "seance_numero": seance["numéro"]
                })
                if not seance_response:
                    continue

                seance_id = seance_response.get("id")

                # 5️⃣ Enregistrement des Exercices
                for exercice in seance["list_exercices"]:
                    exercice_response = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "exercice_nom": exercice["nom"],
                        "exercice_temps_repos": exercice["temps_de_repos"]
                    })
                    if not exercice_response:
                        continue

                    exercice_id = exercice_response.get("id")

                    # 6️⃣ Enregistrement des Séries
                    for serie in exercice["list_série"]:
                        send_to_bubble("create_serie", {
                            "exercice_id": exercice_id,
                            "serie_charge": serie["charge"],
                            "serie_repetitions": serie["répétitions"],
                            "serie_nombre": serie["séries"]
                        })

    return {"message": "Programme enregistré avec succès !"}

# 📌 Endpoint Flask pour gérer la génération du programme
@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

# 📌 Démarrage de l’application Flask
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
