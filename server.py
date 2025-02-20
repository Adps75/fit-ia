from flask import Flask, request, jsonify
import requests
import os
import json
import re  # Pour nettoyer les balises Markdown

app = Flask(__name__)

# ------------------------------------------------------------------------
# Configuration OpenAI et Bubble
# ------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

# Verification des cles
if not OPENAI_API_KEY:
    raise ValueError("Cle API OpenAI manquante ! Ajoutez-la dans les variables d'environnement.")
if not BUBBLE_API_KEY:
    raise ValueError("Cle API Bubble manquante ! Ajoutez-la dans les variables d'environnement.")


# ------------------------------------------------------------------------
# Fonction pour envoyer les donnees a Bubble Backend Workflows
# ------------------------------------------------------------------------

def send_to_bubble(endpoint, payload):
    """
    Envoie les donnees a Bubble avec le header Authorization
    et retourne le JSON de la reponse si status=200.
    """
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    print(f"-> Envoi a Bubble : {url}\nPayload : {json.dumps(payload, indent=2)}")
    print(f"Reponse API Bubble : {response.status_code} | {response.text}")

    if response.status_code == 200:
        return response.json()
    else:
        return None


# ------------------------------------------------------------------------
# Fonction pour nettoyer la reponse JSON d'OpenAI
# ------------------------------------------------------------------------

def clean_json_response(response_text: str) -> str:
    """
    Supprime les balises Markdown (```json ... ```).
    On ne garde que le contenu JSON brut.
    """
    cleaned_text = re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()


# ------------------------------------------------------------------------
# Generation du programme d'entrainement avec OpenAI
# ------------------------------------------------------------------------

def generate_training_program(data):
    """
    Genere un programme structure via OpenAI, en JSON strict.
    Chaque seance comporte 'list_exercices' et chaque exercice 'list_series'.
    """
    prompt = f"""
    Tu es un coach expert en planification d'entrainements.
    Genere un programme d'entrainement EN JSON STRICTEMENT VALIDE, 
    sans commentaire ni texte hors du JSON.
    N'inclus pas d'expressions non numeriques (ex: '10 par jambe') 
    dans des champs numeriques.

    Parametres a prendre en compte :
    - Sport : {data['sport']}
    - Niveau : {data['level']}
    - Frequence : {data['frequency']} fois par semaine
    - Objectif : {data['goal']}
    - Genre : {data['genre']}

    La sortie doit etre uniquement du JSON, ex.:

    {{
      \"programme\": {{
        \"nom\": \"{data.get('programme_nom', 'Programme personnalise')}\",
        \"duree\": {data.get('programme_duree', 12)},
        \"list_cycles\": [...]
      }}
    }}
    Aucune donnee hors du JSON.
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
        print(f"Erreur OpenAI : {response.status_code} | {response.text}")
        return None

    try:
        response_json = response.json()
        print(f"Reponse OpenAI : {json.dumps(response_json, indent=2)}")

        if "choices" not in response_json or not response_json["choices"]:
            print("OpenAI a renvoye une reponse vide.")
            return None

        message_content = response_json["choices"][0]["message"]["content"]
        if not message_content:
            print("OpenAI a renvoye un message vide.")
            return None

        cleaned_json = clean_json_response(message_content)
        return json.loads(cleaned_json)

    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {str(e)}")
        print(f"Reponse brute OpenAI apres nettoyage : {cleaned_json}")
        return None


# ------------------------------------------------------------------------
# Fonction principale pour traiter le programme et l'envoyer a Bubble
# ------------------------------------------------------------------------

def process_training_program(data):
    """
    1. Genere un programme via OpenAI
    2. L'envoie aux differentes API Workflows de Bubble
    3. Cree chaque serie en fonction du champ 'series' => si 'series':3, on cree 3 entrees
    4. Met a jour chaque parent (programme, cycle, semaine, seance, exercice)
       via update_programme, update_cycle, update_semaine, update_seance, update_exercice
    """
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Echec de la generation du programme"}

    # 1) Creation du Programme
    programme_payload = {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_duree": programme_data["programme"]["duree"]  # Remplace "durée" par "duree"
    }
    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]

    programme_response = send_to_bubble("create_programme", programme_payload)
    if not programme_response or "response" not in programme_response or "id" not in programme_response["response"]:
        print(f"Erreur: ID programme manquant dans la reponse Bubble {programme_response}")
        return {"error": "ID programme manquant"}

    programme_id = programme_response["response"]["id"]
    print(f"Programme enregistre avec ID : {programme_id}")

    # Stocke les ID de cycles
    list_cycles_ids = []

    # 2) Parcours des cycles
    if "list_cycles" not in programme_data["programme"]:
        return {"message": "Programme enregistre (aucun cycle)."}

    for cycle in programme_data["programme"]["list_cycles"]:
        cycle_nom = cycle.get("nom", "Cycle sans nom")
        cycle_duree = cycle.get("duree", 1)

        cycle_response = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle_nom,
            "cycle_duree": cycle_duree
        })
        if not cycle_response or "response" not in cycle_response or "id" not in cycle_response["response"]:
            print(f"Erreur: Impossible de creer le cycle {cycle_nom}")
            continue

        cycle_id = cycle_response["response"]["id"]
        list_cycles_ids.append(cycle_id)

        # Stocke les ID de semaines
        list_semaines_ids = []

        # 3) Parcours des semaines
        if "list_semaines" not in cycle:
            continue

        for semaine in cycle["list_semaines"]:
            semaine_numero = semaine.get("numero", 1)
            semaine_response = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine_numero
            })
            if (not semaine_response or
                "response" not in semaine_response or
                "id" not in semaine_response["response"]):
                print(f"Erreur: Impossible de creer la semaine {semaine_numero}")
                continue

            semaine_id = semaine_response["response"]["id"]
            list_semaines_ids.append(semaine_id)

            # Stocke les ID de seances
            list_seances_ids = []

            # 4) Parcours des seances
            if "list_séances" not in semaine:
                continue

            for seance in semaine["list_séances"]:
                seance_nom = seance.get("nom", f"Semaine {semaine_numero} - Seance")
                seance_numero = seance.get("numero", 1)

                seance_response = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance_nom,
                    "seance_numero": seance_numero
                })
                if (not seance_response or
                    "response" not in seance_response or
                    "id" not in seance_response["response"]):
                    print(f"Erreur: Impossible de creer la seance {seance_nom}")
                    continue

                seance_id = seance_response["response"]["id"]
                list_seances_ids.append(seance_id)

                # 5) Parcours des Exercices
                if "list_exercices" not in seance:
                    continue

                # Stocke les ID d'exercices
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
                        print(f"Erreur: Impossible de creer l'exercice {exercice_nom}")
                        continue

                    exercice_id = exercice_response["response"]["id"]
                    list_exos_ids.append(exercice_id)

                    # 6) Parcours des Series
                    if "list_séries" not in exercice:
                        continue

                    # Stocke les ID de series
                    list_series_ids = []

                    for serie_obj in exercice["list_séries"]:
                        # Nombre de sets => si 'séries':3 => on cree 3 entrees
                        nb_sets = serie_obj.get("séries", 1)
                        serie_charge = str(serie_obj.get("charge", 0))
                        serie_reps = serie_obj.get("répétitions", 0)

                        for _ in range(nb_sets):
                            serie_response = send_to_bubble("create_serie", {
                                "exercice_id": exercice_id,
                                "serie_charge": serie_charge,
                                "serie_repetitions": serie_reps,
                                "serie_nombre": 1  # 1 entree par set
                            })
                            if serie_response and "id" in serie_response["response"]:
                                list_series_ids.append(serie_response["response"]["id"])

                    # update_exercice
                    if list_series_ids:
                        send_to_bubble("update_exercice", {
                            "id": exercice_id,
                            "list_series": list_series_ids
                        })

                # update_seance
                if list_exos_ids:
                    send_to_bubble("update_seance", {
                        "id": seance_id,
                        "list_exercices": list_exos_ids
                    })

            # update_semaine
            if list_seances_ids:
                send_to_bubble("update_semaine", {
                    "id": semaine_id,
                    "list_seances": list_seances_ids
                })

        # update_cycle
        if list_semaines_ids:
            send_to_bubble("update_cycle", {
                "id": cycle_id,
                "list_semaines": list_semaines_ids
            })

    # update_programme
    if list_cycles_ids:
        send_to_bubble("update_programme", {
            "id": programme_id,
            "list_cycles": list_cycles_ids
        })

    return {"message": "Programme enregistre avec succes!"}


# ------------------------------------------------------------------------
# Endpoint Flask pour gerer la generation du programme
# ------------------------------------------------------------------------

@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500


# ------------------------------------------------------------------------
# Demarrage de l'application Flask
# ------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
