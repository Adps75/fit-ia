from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)

# 🔹 Configuration OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# 🔹 Configuration Bubble API
BUBBLE_API_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf"
BUBBLE_HEADERS = {"Content-Type": "application/json"}

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
        series_count=4,  # Nombre de séries par défaut
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
        return json.loads(response.json()["choices"][0]["message"]["content"])
    else:
        return None

def send_to_bubble(endpoint, data):
    """ 🔥 Envoie les données vers Bubble """
    response = requests.post(f"{BUBBLE_API_BASE_URL}/{endpoint}", json=data, headers=BUBBLE_HEADERS)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Erreur sur {endpoint}: {response.text}")
        return None

@app.route("/generate-program", methods=["POST"])
def generate_program():
    """ 📌 Génère un programme et l'enregistre dans Bubble """
    data = request.json
    program_data = generate_training_program(data)

    if not program_data:
        return jsonify({"error": "Échec de la génération du programme"}), 500

    # 1️⃣ Enregistrer le Programme
    programme_response = send_to_bubble("create_programme", {
        "nom": program_data["programme"]["nom"],
        "durée": program_data["programme"]["durée"]
    })
    
    if not programme_response:
        return jsonify({"error": "Échec de la création du programme"}), 500

    programme_id = programme_response.get("id")

    # 2️⃣ Enregistrer les Cycles
    for cycle in program_data["programme"]["list_cycles"]:
        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "nom": cycle["nom"],
            "durée": cycle["durée"]
        })
        if not cycle_response:
            continue

        cycle_id = cycle_response.get("id")

        # 3️⃣ Enregistrer les Semaines
        for semaine in cycle["list_semaines"]:
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "numéro": semaine["numéro"]
            })
            if not semaine_response:
                continue

            semaine_id = semaine_response.get("id")

            # 4️⃣ Enregistrer les Séances
            for seance in semaine["list_séances"]:
                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "nom": seance["nom"],
                    "numéro": seance["numéro"]
                })
                if not seance_response:
                    continue

                seance_id = seance_response.get("id")

                # 5️⃣ Enregistrer les Exercices
                for exercice in seance["list_exercices"]:
                    exercice_response = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "nom": exercice["nom"],
                        "temps_de_repos": exercice["temps_de_repos"]
                    })
                    if not exercice_response:
                        continue

                    exercice_id = exercice_response.get("id")

                    # 6️⃣ Enregistrer les Séries
                    for serie in exercice["list_série"]:
                        send_to_bubble("create_serie", {
                            "exercice_id": exercice_id,
                            "charge": serie["charge"],
                            "répétitions": serie["répétitions"],
                            "séries": serie["séries"]
                        })

    return jsonify({"message": "Programme enregistré avec succès !"}), 201

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render assigne un port automatiquement
    app.run(host="0.0.0.0", port=port, debug=False)
