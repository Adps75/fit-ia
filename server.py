from flask import Flask, request, jsonify
import requests
import os
import json
import re  # Pour nettoyer les balises Markdown

app = Flask(__name__)

# ------------------------------------------------------------------------
# Configuration ASCII ONLY (pas d'accents / emojis)
# ------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Cle API OpenAI manquante")
if not BUBBLE_API_KEY:
    raise ValueError("Cle API Bubble manquante")

# ------------------------------------------------------------------------
# Envoi a Bubble
# ------------------------------------------------------------------------

def send_to_bubble(endpoint, payload):
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    response = requests.post(url, json=payload, headers=headers)
    print(f"-> Envoi a Bubble : {url}\nPayload : {json.dumps(payload, indent=2)}")
    print(f"Reponse: {response.status_code} | {response.text}")
    if response.status_code == 200:
        return response.json()
    else:
        return None

# ------------------------------------------------------------------------
# Nettoyage du JSON
# ------------------------------------------------------------------------

def clean_json_response(response_text: str) -> str:
    cleaned_text = re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL)
    return cleaned_text.strip()

# ------------------------------------------------------------------------
# Generation du programme via OpenAI
# ------------------------------------------------------------------------

def generate_training_program(data):
    prompt = f"""
    Tu es un coach expert en planification d'entrainements.
    Genere un programme d'entrainement EN JSON STRICTEMENT VALIDE, 
    sans commentaire ni texte hors du JSON.
    Pas de '10 par jambe' dans des champs numeriques.

    Parametres:
    - Sport: {data['sport']}
    - Niveau: {data['level']}
    - Frequence: {data['frequency']} fois/semaine
    - Objectif: {data['goal']}
    - Genre: {data['genre']}

    Sortie = JSON valide, ex.:
    {{
      \"programme\": {{
        \"nom\": \"{data.get('programme_nom', 'Programme perso')}\",
        \"duree\": {data.get('programme_duree', 12)},
        \"list_cycles\": [ ... ]
      }}
    }}
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
        if "choices" not in response_json or not response_json["choices"]:
            return None
        message_content = response_json["choices"][0]["message"]["content"]
        if not message_content:
            return None
        cleaned_json = clean_json_response(message_content)
        return json.loads(cleaned_json)
    except json.JSONDecodeError:
        return None

# ------------------------------------------------------------------------
# Process principal: creation & association
# ------------------------------------------------------------------------

def process_training_program(data):
    programme_data = generate_training_program(data)
    if not programme_data:
        return {"error": "Echec generation programme"}

    # 1) Creation Programme
    programme_payload = {
        "programme_nom": programme_data["programme"]["nom"],
        "programme_duree": programme_data["programme"]["duree"]
    }
    if "user_id" in data:
        programme_payload["user_id"] = data["user_id"]

    prog_resp = send_to_bubble("create_programme", programme_payload)
    if not prog_resp or "id" not in prog_resp.get("response", {}):
        return {"error": "ID programme manquant"}
    programme_id = prog_resp["response"]["id"]

    # Stock IDs cycles
    list_cycles_ids = []

    # 2) cycles
    for cycle in programme_data["programme"].get("list_cycles", []):
        cycle_resp = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle.get("nom", "Cycle"),
            "cycle_duree": cycle.get("duree", 1)
        })
        if not cycle_resp or "id" not in cycle_resp.get("response", {}):
            continue
        cycle_id = cycle_resp["response"]["id"]
        list_cycles_ids.append(cycle_id)

        # Stock IDs semaines
        list_semaines_ids = []

        # 3) semaines
        for semaine in cycle.get("list_semaines", []):
            semaine_resp = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": semaine.get("numero", 1)
            })
            if not semaine_resp or "id" not in semaine_resp.get("response", {}):
                continue
            semaine_id = semaine_resp["response"]["id"]
            list_semaines_ids.append(semaine_id)

            # Stock IDs seances
            list_seances_ids = []

            # 4) seances
            for seance in semaine.get("list_séances", []):
                seance_nom = seance.get("nom", "Seance")
                seance_resp = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": seance_nom,
                    "seance_numero": seance.get("numero", 1)
                })
                if not seance_resp or "id" not in seance_resp.get("response", {}):
                    continue
                seance_id = seance_resp["response"]["id"]
                list_seances_ids.append(seance_id)

                # Stock IDs exercices
                list_exos_ids = []

                # 5) exercices
                for exercice in seance.get("list_exercices", []):
                    exo_nom = exercice.get("nom", "Exercice")
                    exo_temps = exercice.get("temps_de_repos", 60)
                    exo_resp = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "exercice_nom": exo_nom,
                        "exercice_temps_repos": exo_temps
                    })
                    if not exo_resp or "id" not in exo_resp.get("response", {}):
                        continue
                    exo_id = exo_resp["response"]["id"]
                    list_exos_ids.append(exo_id)

                    # Stock IDs series
                    list_series_ids = []

                    # 6) series
                    for serie_obj in exercice.get("list_séries", []):
                        nb_sets = serie_obj.get("séries", 1)
                        serie_charge = str(serie_obj.get("charge", 0))
                        serie_reps = serie_obj.get("répétitions", 0)

                        # On cree nb_sets entrees distinctes
                        for i in range(nb_sets):
                            serie_nom = f"Serie {i+1}"
                            serie_resp = send_to_bubble("create_serie", {
                                "exercice_id": exo_id,
                                "serie_nom": serie_nom,
                                "serie_charge": serie_charge,
                                "serie_repetitions": serie_reps,
                                "serie_nombre": 1
                            })
                            if serie_resp and "id" in serie_resp["response"]:
                                list_series_ids.append(serie_resp["response"]["id"])

                    # update_exercice
                    if list_series_ids:
                        send_to_bubble("update_exercice", {
                            "id": exo_id,
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


@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
