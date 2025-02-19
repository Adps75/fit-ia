from flask import Flask, request, jsonify
import requests
import os
import re  # Ajout pour nettoyer les balises Markdown JSON

app = Flask(__name__)

# Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Configuration Bubble
BUBBLE_API_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/obj"

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

def clean_json_response(response_text):
    """ Supprime les balises Markdown pour extraire uniquement le JSON """
    cleaned_text = re.sub(r"```json\\n(.*?)\\n```", r"\1", response_text, flags=re.DOTALL).strip()
    return cleaned_text

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
        raw_content = response.json()["choices"][0]["message"]["content"]
        return clean_json_response(raw_content)
    else:
        return None

@app.route("/analyse-progress", methods=["POST"])
def analyse_progress():
    """ Analyse les performances et ajuste les charges pour la semaine suivante """
    data = request.json

    # Préparation des inputs pour l'IA
    prompt = f"""
    Tu es un coach de suivi personnalisé.
    Voici les performances de l'utilisateur pour la semaine {data["current_week"]} :
    {data["performance_data"]}
    
    Génère les charges et répétitions pour la semaine suivante en ajustant selon la progression.
    """

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Tu es un coach expert en analyse sportive."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    
    if response.status_code == 200:
        raw_content = response.json()["choices"][0]["message"]["content"]
        return jsonify({"updated_plan": clean_json_response(raw_content)}), 200
    else:
        return jsonify({"error": "Échec de l'analyse"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
