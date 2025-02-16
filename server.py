from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# 🔹 Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# 🔹 Vérification de la clé API OpenAI
if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")

# 📌 Prompt pour la génération du programme d'entraînement
PROMPT_TEMPLATE = """Tu es un coach expert en préparation physique et en planification de programmes sportifs. 
Génère un programme d'entraînement structuré en cycles et semaines sous un format JSON bien défini.

Génère un programme d'entraînement détaillé en respectant cette structure :
{{
  "programme": {{
    "nom": "Programme personnalisé",
    "durée": "{duration} semaines",
    "list_cycles": [
      {{
        "nom": "Nom du cycle",
        "durée": "{cycle_duration} semaines",
        "list_semaines": [
          {{
            "numéro": 1,
            "list_séances": [
              {{
                "nom": "Nom de la séance",
                "numéro": 1,
                "list_exercices": [
                  {{
                    "nom": "Nom de l'exercice",
                    "list_série": [
                      {{
                        "séries": {series_count},
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
    """ 🔥 Génère un programme d'entraînement via OpenAI API """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    user_prompt = PROMPT_TEMPLATE.format(
        sport=data["sport"],
        level=data["level"],
        frequency=data["frequency"],
        goal=data["goal"],
        duration=data.get("duration", "12"),  # L'IA décide si non fourni
        cycle_duration=data.get("cycle_duration", "4"),
        charge="75% 1RM",
        repetitions=8,
        rest_time=90,
        genre=data.get("genre", "Non spécifié")  
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

@app.route("/generate-program", methods=["POST"])
def generate_program():
    """ 📌 Endpoint pour générer un programme et renvoyer les données à Bubble """
    data = request.json
    program_json = generate_training_program(data)

    if program_json:
        try:
            program_data = eval(program_json)  # 🔥 Convertir le JSON string en dictionnaire Python
            return jsonify(program_data), 201  # Renvoie le programme complet à Bubble
        except Exception as e:
            return jsonify({"error": f"Erreur de traitement : {str(e)}"}), 500
    else:
        return jsonify({"error": "Échec de la génération du programme"}), 500

@app.route("/analyse-progress", methods=["POST"])
def analyse_progress():
    """ 🔥 Analyse les performances et ajuste les charges pour la semaine suivante """
    data = request.json

    prompt = f"""
    Tu es un coach de suivi personnalisé.
    Voici les performances de l'utilisateur pour la semaine {data["current_week"]} :
    {data["performance_data"]}
    
    Génère uniquement les charges et répétitions des séances de la semaine suivante.
    """

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Tu es un coach expert en suivi d'entraînement."},
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
        return jsonify({"updated_plan": response.json()["choices"][0]["message"]["content"]}), 200
    else:
        return jsonify({"error": "Échec de l'analyse"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render assigne un port automatiquement
    app.run(host="0.0.0.0", port=port, debug=False)
