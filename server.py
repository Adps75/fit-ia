from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)

# 🔹 Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# 🔹 Configuration Bubble
BUBBLE_BASE_URL = "https://ton-app.bubbleapps.io/version-test/api/1.1/wf/"

# 🔹 Vérification des clés API
if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")

# 📌 Fonction pour envoyer les données à Bubble Backend Workflows
def send_to_bubble(endpoint, payload):
    url = BUBBLE_BASE_URL + endpoint
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

# 📌 Génération du programme d'entraînement avec OpenAI
def generate_training_program(data):
    prompt = f"""
    Tu es un coach expert en préparation physique et en planification de programmes sportifs.
    Génère un programme d'entraînement structuré en cycles et semaines sous un format JSON bien défini.

    Paramètres :
    - Sport : {data["sport"]}
    - Niveau : {data["level"]}
    - Fréquence d'entraînement : {data["frequency"]} fois par semaine
    - Objectif : {data["goal"]}
    - Genre : {data["genre"]}

    Retourne un JSON sans texte additionnel :
    {{
      "programme": {{
        "nom": "{data.get('programme_nom', 'Programme personnalisé')}",
        "durée": {data.get('programme_duree', 12)},
        "list_cycles": [...]
      }}
    }}
    """

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}

    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)

    if response.status_code == 200:
        return json.loads(response.json()["choices"][0]["message"]["content"])
    else:
        return None

# 📌 Fonction principale pour traiter le programme et l'envoyer à Bubble
def process_training_program(data):
    programme_data = generate_training_program(data)

    if not programme_data:
        return {"error": "Échec de la génération du programme"}

    # 1️⃣ Enregistrement du Programme
    programme_response = send_to_bubble("create_programme", {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_durée": programme_data["programme"]["durée"]
    })

    programme_id = programme_response.get("id")

    # 2️⃣ Enregistrement des Cycles
    for cycle in programme_data["programme"]["list_cycles"]:
        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle["nom"],
            "cycle_durée": cycle["durée"]
        })
        cycle_id = cycle_response.get("id")

        # 3️⃣ Enregistrement des Semaines
        for semaine in cycle["list_semaines"]:
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine["numéro"]
            })
            semaine_id = semaine_response.get("id")

            # 4️⃣ Enregistrement des Séances
            for seance in semaine["list_séances"]:
                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance["nom"],
                    "seance_numero": seance["numéro"]
                })
                seance_id = seance_response.get("id")

                # 5️⃣ Enregistrement des Exercices
                for exercice in seance["list_exercices"]:
                    exercice_response = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "exercice_nom": exercice["nom"],
                        "exercice_temps_repos": exercice["temps_de_repos"]
                    })
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
