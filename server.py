from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Configuration Bubble (Assure-toi que l'API Data est activée sur Bubble)
BUBBLE_API_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/obj/programme"

# Prompt pour la génération du programme
PROMPT_TEMPLATE = """Tu es un coach expert en préparation physique et en planification de programmes sportifs. 
Ton objectif est de générer des programmes d'entraînement structurés sur plusieurs cycles et semaines, sous un format JSON bien défini.

Génère un programme d'entraînement détaillé en respectant cette structure :
{{
  "programme": {{
    "durée": "{duration} semaines",
    "list_cycles": [
      {{
        "nom": "Nom du cycle",
        "durée": "{cycle_duration} semaines",
        "list_semaines": [
          {{
            "numéro": {week_number},
            "list_séances": [
              {{
                "nom": "Nom de la séance",
                "numéro": {session_number},
                "list_exercices": [
                  {{
                    "nom": "Nom de l'exercice",
                    "list_série": [
                      {{
                        "charge": "{charge}",
                        "répétitions": {repetitions}
                      }}
                    ],
                    "temps_de_repos": "{rest_time} secondes"
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

Paramètres :
- Sport : {sport}
- Niveau : {level}
- Fréquence d'entraînement : {frequency} fois par semaine
- Objectif : {goal}
- Genre : {genre}

⚠️ **IMPORTANT** : 
- **Ne pas inclure de texte explicatif avant ou après le JSON.**
- **Ne pas entourer la réponse avec des balises Markdown.**
- **Renvoyer uniquement le JSON brut, sans texte additionnel.**
"""

def generate_training_program(data):
    """ Génère un programme d'entraînement via OpenAI API """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    user_prompt = PROMPT_TEMPLATE.format(
        sport=data["sport"],
        level=data["level"],
        frequency=data["frequency"],
        goal=data["goal"],
        duration=data["duration"],
        cycle_duration=data["cycle_duration"],
        week_number=1,
        session_number=1,
        charge="75% 1RM",
        repetitions=8,
        rest_time=90
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Tu es un coach expert en programmation sportive."},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return None

def save_to_bubble(program_data):
    """ Envoie les données générées vers Bubble API """
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(BUBBLE_API_URL, json=program_data, headers=headers)
    
    return response.status_code, response.text  # On retourne aussi la réponse de Bubble pour debug

@app.route("/generate-program", methods=["POST"])
def generate_program():
    """ Endpoint pour générer et enregistrer un programme """
    data = request.json
    program_json = generate_training_program(data)

    if program_json:
        program_data = {"programme_data": program_json, "user_id": data["user_id"]}
        status_code, response_text = save_to_bubble(program_data)

        if status_code == 201:
            return jsonify({"message": "Programme enregistré avec succès !"}), 201
        else:
            return jsonify({"error": "Erreur lors de l'enregistrement sur Bubble", "details": response_text}), 500
    else:
        return jsonify({"error": "Échec de la génération du programme"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
