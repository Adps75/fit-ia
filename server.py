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
    cleaned_text = re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Génération du programme d'entraînement avec OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def generate_training_program(data):
    """
    Génère un programme structuré via OpenAI, en JSON strict.
    Nous imposons ici que chaque séance comporte un "list_exercices"
    et chaque exercice un "list_séries".
    """
    prompt = f"""
    Tu es un coach expert en planification d'entraînements.
    Génère un programme d'entraînement EN JSON STRICTEMENT VALIDE, 
    sans commentaire ni texte hors du JSON.
    N'inclus pas d'expressions non numériques (p. ex. "10 par jambe") 
    dans des champs numériques.

    Paramètres à prendre en compte :
    - Sport : {data["sport"]}
    - Niveau : {data["level"]}
    - Fréquence : {data["frequency"]} fois par semaine
    - Objectif : {data["goal"]}
    - Genre : {data["genre"]}

    La sortie doit être uniquement du JSON, avec la structure suivante :
    Chaque séance possède un champ "list_exercices", 
    et chaque exercice possède un champ "list_séries" (un tableau d'objets).

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
    Aucune donnée hors du JSON.
    """

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",  # ou autre modèle
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

        # Vérification de la présence du champ "choices"
        if "choices" not in response_json or not response_json["choices"]:
            print("❌ OpenAI a renvoyé une réponse vide.")
            return None

        message_content = response_json["choices"][0]["message"]["content"]
        if not message_content:
            print("❌ OpenAI a renvoyé un message vide.")
            return None

        # Nettoyage du Markdown
        cleaned_json = clean_json_response(message_content)

        # Parsing en JSON Python
        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        print(f"❌ Erreur JSON : {str(e)}")
        print(f"🔍 Réponse brute OpenAI après nettoyage : {cleaned_json}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Fonction principale pour traiter le programme et l'envoyer à Bubble
# ─────────────────────────────────────────────────────────────────────────────

def process_training_program(data):
    """
    1. Génère un programme via OpenAI
    2. L'envoie aux différentes API Workflows de Bubble
    3. Crée chaque série en fonction du champ 'séries' → si 'séries':3, on crée 3 entrées
    4. Met à jour chaque parent (programme, cycle, semaine, séance, exercice) 
       via update_programme, update_cycle, update_semaine, update_seance, update_exercice
    """
    # Génération du JSON via OpenAI
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Échec de la génération du programme"}

    # 1️⃣ Création du Programme
    programme_payload = {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_durée": programme_data["programme"]["durée"]
    }
    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]

    programme_response = send_to_bubble("create_programme", programme_payload)
    if not programme_response or "response" not in programme_response or "id" not in programme_response["response"]:
        print(f"❌ Erreur : ID programme manquant dans la réponse Bubble {programme_response}")
        return {"error": "ID programme manquant"}

    programme_id = programme_response["response"]["id"]
    print(f"✅ Programme enregistré avec ID : {programme_id}")

    # Stocke les ID de cycles pour update_programme
    list_cycles_ids = []

    # 2️⃣ Parcours des cycles
    if "list_cycles" not in programme_data["programme"]:
        return {"message": "Programme enregistré (aucun cycle renseigné)."}

    for cycle in programme_data["programme"]["list_cycles"]:
        cycle_nom = cycle.get("nom", "Cycle sans nom")
        cycle_duree = cycle.get("durée", 1)

        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle_nom,
            "cycle_durée": cycle_duree
        })
        if not cycle_response or "response" not in cycle_response or "id" not in cycle_response["response"]:
            print(f"❌ Erreur : Impossible de créer le cycle {cycle_nom}")
            continue

        cycle_id = cycle_response["response"]["id"]
        list_cycles_ids.append(cycle_id)

        # Stocke les ID de semaines pour update_cycle
        list_semaines_ids = []

        # 3️⃣ Parcours des semaines
        if "list_semaines" not in cycle:
            continue

        for semaine in cycle["list_semaines"]:
            semaine_numero = semaine.get("numéro", 1)
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine_numero
            })
            if (not semaine_response or 
                "response" not in semaine_response or 
                "id" not in semaine_response["response"]):
                print(f"❌ Erreur : Impossible de créer la semaine {semaine_numero}")
                continue

            semaine_id = semaine_response["response"]["id"]
            list_semaines_ids.append(semaine_id)

            # Stocke les ID de séances pour update_semaine
            list_seances_ids = []

            # 4️⃣ Parcours des séances
            if "list_séances" not in semaine:
                continue

            for seance in semaine["list_séances"]:
                seance_nom = seance.get("nom", f"Semaine {semaine_numero} - Séance")
                seance_numero = seance.get("numéro", 1)

                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance_nom,
                    "seance_numero": seance_numero
                })
                if (not seance_response or 
                    "response" not in seance_response or 
                    "id" not in seance_response["response"]):
                    print(f"❌ Erreur : Impossible de créer la séance {seance_nom}")
                    continue

                seance_id = seance_response["response"]["id"]
                list_seances_ids.append(seance_id)

                # 5️⃣ Parcours des Exercices
                if "list_exercices" not in seance:
                    continue

                # Stocke les ID d'exercices pour update_seance
                list_exos_ids = []

                for exercice in seance["list_exercices"]:
                    exercice_nom = exercice.get("nom", "Exercice")
                    exercice_temps = exercice.get("temps_de_repos", 60)

                    exercice_response = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "exercice_nom": exercice_nom,
                        "exercice_temps_repos": exercice_temps
                    })
                    if (not exercice_response or 
                        "response" not in exercice_response or 
                        "id" not in exercice_response["response"]):
                        print(f\"❌ Erreur : Impossible de créer l'exercice {exercice_nom}\")
                        continue

                    exercice_id = exercice_response["response"]["id"]
                    list_exos_ids.append(exercice_id)

                    # 6️⃣ Parcours des Séries
                    if "list_séries" not in exercice:
                        continue

                    # Stocke les ID de séries pour update_exercice
                    list_series_ids = []

                    for serie_obj in exercice["list_séries"]:
                        # Nombre de séries => si \"séries\" = 3 => on crée 3 lignes
                        nb_sets = serie_obj.get("séries", 1)
                        serie_charge = str(serie_obj.get("charge", 0))  # en str
                        serie_reps = serie_obj.get("répétitions", 0)

                        for _ in range(nb_sets):
                            serie_response = send_to_bubble("create_serie", {
                                "exercice_id": exercice_id,
                                "serie_charge": serie_charge,
                                "serie_repetitions": serie_reps,
                                "serie_nombre": 1  # On crée 1 entrée par set
                            })
                            if serie_response and "id" in serie_response["response"]:
                                list_series_ids.append(serie_response["response"]["id"])

                    # update_exercice : on ajoute la liste des séries
                    if list_series_ids:
                        send_to_bubble("update_exercice", {
                            "id": exercice_id,
                            "list_séries": list_series_ids
                        })

                # update_seance : on ajoute la liste des exercices
                if list_exos_ids:
                    send_to_bubble("update_seance", {
                        "id": seance_id,
                        "list_exercices": list_exos_ids
                    })

            # update_semaine : on ajoute la liste des séances
            if list_seances_ids:
                send_to_bubble("update_semaine", {
                    "id": semaine_id,
                    "list_seances": list_seances_ids
                })

        # update_cycle : on ajoute la liste des semaines
        if list_semaines_ids:
            send_to_bubble("update_cycle", {
                "id": cycle_id,
                "list_semaines": list_semaines_ids
            })

    # update_programme : on ajoute la liste des cycles
    if list_cycles_ids:
        send_to_bubble("update_programme", {
            "id": programme_id,
            "list_cycles": list_cycles_ids
        })

    return {"message": "Programme enregistré avec succès !"}


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Endpoint Flask pour gérer la génération du programme
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    # Retourne 201 si tout s'est bien passé, sinon 500
    return jsonify(result), 201 if "message" in result else 500


# ─────────────────────────────────────────────────────────────────────────────
# 📌 Démarrage de l’application Flask
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
