from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# 🔑 Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# 📌 Vérification de la clé API
if not OPENAI_API_KEY:
    raise ValueError("❌ Clé API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")

# 📌 Prompt dynamique pour générer le programme
PROMPT_TEMPLATE = """
Tu es un coach expert en préparation physique et en planification de programmes sportifs. 
Génère un programme d'entraînement structuré en cycles et semaines sous un format JSON bien défini.

Le programme doit respecter la structure suivante :
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

🔹 **Contraintes :**  
- L'IA définit dynamiquement **le nombre de semaines, cycles et séances**.  
- **Les charges ne sont définies que pour la première semaine.**  
- **Chaque semaine, une analyse adapte les charges et répétitions.**  

📌 **Profil utilisateur :**
- Sport : {sport}
- Niveau : {level}
- Fréquence d'entraînement : {frequency} fois par semaine
- Objectif : {goal}
- Genre : {genre}

⚠️ **IMPORTANT :**  
- **Ne pas inclure de texte explicatif avant ou après le JSON.**  
- **Ne pas entourer la réponse avec des balises Markdown.**  
- **Renvoyer uniquement le JSON brut.**
"""

def generate_training_program(data):
    """ 🔥 Génère un programme d'entraînement personnalisé """
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
        week_number=1,
        session_number=1,
        charge="75% 1RM",  # **Uniquement pour la première semaine**
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

@app.route("/generate-program", methods=["POST"])
def generate_program():
    """ 📌 API pour générer un programme et le retourner """
    data = request.json

    # 🚨 Vérification des données reçues
    required_fields = ["sport", "level", "frequency", "goal", "genre"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Données utilisateur incomplètes"}), 400

    program_json = generate_training_program(data)

    if program_json:
        return jsonify({"programme": program_json}), 201
    else:
        return jsonify({"error": "Échec de la génération du programme"}), 500

@app.route("/analyse-progress", methods=["POST"])
def analyse_progress():
    """ 📊 Analyse les performances et ajuste les charges pour la semaine suivante """
    data = request.json

    if "current_week" not in data or "performance_data" not in data:
        return jsonify({"error": "Données manquantes"}), 400

    prompt = f"""
    Tu es un coach de suivi personnalisé.
    Voici les performances de l'utilisateur pour la semaine {data["current_week"]} :
    {data["performance_data"]}

    🔹 **Mission :**
    - Analyse ces résultats et ajuste les charges et répétitions pour la semaine suivante.
    - Renvoye uniquement un JSON avec la mise à jour des charges et répétitions.
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
        return jsonify({"updated_plan": response.json()["choices"][0]["message"]["content"]}), 200
    else:
        return jsonify({"error": "Échec de l'analyse"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render assigne un port automatique
    app.run(host="0.0.0.0", port=port, debug=False)
