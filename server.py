from flask import Flask, request, jsonify
import requests
import os
import json
import re

app = Flask(__name__)

# ---------------------------------------------------
# Configuration OpenAI et Bubble (ASCII only)
# ---------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY in environment.")
if not BUBBLE_API_KEY:
    raise ValueError("Missing BUBBLE_API_KEY in environment.")


def send_to_bubble(endpoint, payload):
    """
    Envoie les donnees a Bubble via workflows.
    """
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    resp = requests.post(url, json=payload, headers=headers)
    print("-> Envoi a Bubble :", url)
    print("Payload :", json.dumps(payload, indent=2))
    print("Reponse code:", resp.status_code)
    print("Reponse text:", resp.text)
    if resp.status_code == 200:
        return resp.json()
    return None


def clean_json_response(response_text):
    """
    Retire balises ```json ... ```
    """
    return re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL).strip()


# ---------------------------------------------------
# 1) GENERATE PROGRAM (ENTRAINEMENT)
# ---------------------------------------------------

def generate_training_program(data):
    """
    Genere un JSON strict contenant:
    - programme.duree (int ou float)
    - list_cycles[].duree (int ou float)
    - list_semaines
    - list_seances
    - list_exercices
    - list_series
    """
    prompt = f"""
    Tu es un coach expert en planification d'entrainements.
    Genere un programme d'entrainement EN JSON STRICTEMENT VALIDE,
    sans texte hors du JSON et sans accents.
    
    Important:
    - Utilise la cle 'duree' (sans accent) pour le programme et chaque cycle.
    - Pour le programme: champ 'nom' (string) et 'duree' (int).
    - Pour chaque cycle: champ 'nom' (string) et 'duree' (int).
    - list_semaines[].numero
    - list_semaines[].list_seances
    - Pour chaque seance: cle 'numero', list_exercices
    - Pour chaque exercice: cle 'nom', 'temps_de_repos', list_series
    - Pour chaque serie: cle 'charge', 'repetitions', 'series'
      (et si 'series'=3, nous creerons 3 series en base).
    
    Parametres:
      Sport: {data['sport']}
      Niveau: {data['level']}
      Frequence: {data['frequency']} / semaine
      Objectif: {data['goal']}
      Genre: {data['genre']}

    Sortie exemple:
    {{
      \"programme\": {{
        \"nom\": \"Mon Programme\",
        \"duree\": 12,
        \"list_cycles\": [
          {{
            \"nom\": \"Cycle 1\",
            \"duree\": 4,
            \"list_semaines\": [
              {{
                \"numero\": 1,
                \"list_seances\": [
                  {{
                    \"numero\": 1,
                    \"list_exercices\": [
                      {{
                        \"nom\": \"Exercice 1\",
                        \"temps_de_repos\": 60,
                        \"list_series\": [
                          {{\"charge\": 40, \"repetitions\": 10, \"series\": 3}}
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
    resp = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    if resp.status_code != 200:
        print("Erreur OpenAI:", resp.status_code, resp.text)
        return None

    try:
        rjson = resp.json()
        if "choices" not in rjson or not rjson["choices"]:
            return None
        content = rjson["choices"][0]["message"]["content"]
        cleaned = clean_json_response(content)
        return json.loads(cleaned)
    except:
        return None


def process_training_program(data):
    """
    1) Cree programme => requiert 'duree' dans le JSON
    2) Cree cycles => requiert 'duree' dans chaque cycle
    3) Cree semaines, seances, exercices
    4) Cree series en multipliant par 'series'
    5) update_*
    """
    prog_data = generate_training_program(data)
    if not prog_data:
        return {"error": "Echec generation programme"}

    # Lecture
    prog_obj = prog_data["programme"]
    prog_payload = {
        "programme_nom": prog_obj["nom"],
        "programme_duree": prog_obj["duree"]  # 'duree' doit exister
    }
    if "user_id" in data:
        prog_payload["user_id"] = data["user_id"]

    resp_prog = send_to_bubble("create_programme", prog_payload)
    if not resp_prog or "id" not in resp_prog.get("response", {}):
        return {"error": "ID programme manquant"}
    programme_id = resp_prog["response"]["id"]

    list_cycles = []

    # Parcours cycles
    for c in prog_obj.get("list_cycles", []):
        cyc_payload = {
            "programme_id": programme_id,
            "cycle_nom": c.get("nom", "Cycle"),
            "cycle_duree": c.get("duree", 1)
        }
        cyc_resp = send_to_bubble("create_cycle", cyc_payload)
        if not cyc_resp or "id" not in cyc_resp.get("response", {}):
            continue
        cycle_id = cyc_resp["response"]["id"]
        list_cycles.append(cycle_id)

        list_semaines = []

        for s in c.get("list_semaines", []):
            s_payload = {
                "cycle_id": cycle_id,
                "semaine_numero": s.get("numero", 1)
            }
            s_resp = send_to_bubble("create_semaine", s_payload)
            if not s_resp or "id" not in s_resp.get("response", {}):
                continue
            semaine_id = s_resp["response"]["id"]
            list_semaines.append(semaine_id)

            list_seances = []

            for sea in s.get("list_seances", []):
                sea_payload = {
                    "semaine_id": semaine_id,
                    "seance_nom": sea.get("nom", "Seance"),
                    "seance_numero": sea.get("numero", 1)
                }
                sea_resp = send_to_bubble("create_seance", sea_payload)
                if not sea_resp or "id" not in sea_resp.get("response", {}):
                    continue
                seance_id = sea_resp["response"]["id"]
                list_seances.append(seance_id)

                list_exos = []
                for exo in sea.get("list_exercices", []):
                    exo_payload = {
                        "seance_id": seance_id,
                        "exercice_nom": exo.get("nom", "Exo"),
                        "exercice_temps_repos": exo.get("temps_de_repos", 60)
                    }
                    exo_resp = send_to_bubble("create_exercice", exo_payload)
                    if not exo_resp or "id" not in exo_resp.get("response", {}):
                        continue
                    exo_id = exo_resp["response"]["id"]
                    list_exos.append(exo_id)

                    list_series_ids = []
                    for serie_obj in exo.get("list_series", []):
                        sets_count = serie_obj.get("series", 1)
                        sc = str(serie_obj.get("charge", 0))
                        reps = serie_obj.get("repetitions", 0)
                        for i in range(sets_count):
                            serie_name = f"Serie {i+1}"
                            s_resp2 = send_to_bubble("create_serie", {
                                "exercice_id": exo_id,
                                "serie_nom": serie_name,
                                "serie_charge": sc,
                                "serie_repetitions": reps,
                                "serie_nombre": 1
                            })
                            if s_resp2 and "id" in s_resp2["response"]:
                                list_series_ids.append(s_resp2["response"]["id"])

                    # update_exercice
                    if list_series_ids:
                        send_to_bubble("update_exercice", {
                            "id": exo_id,
                            "list_series": list_series_ids
                        })

                # update_seance
                if list_exos:
                    send_to_bubble("update_seance", {
                        "id": seance_id,
                        "list_exercices": list_exos
                    })

            # update_semaine
            if list_seances:
                send_to_bubble("update_semaine", {
                    "id": semaine_id,
                    "list_seances": list_seances
                })

        # update_cycle
        if list_semaines:
            send_to_bubble("update_cycle", {
                "id": cycle_id,
                "list_semaines": list_semaines
            })

    # update_programme
    if list_cycles:
        send_to_bubble("update_programme", {
            "id": programme_id,
            "list_cycles": list_cycles
        })

    return {"message": "Programme cree avec succes!"}


@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

# ---------------------------------------------------
# 2) GENERATE NUTRITION
# ---------------------------------------------------

def generate_nutrition_json(data):
    """
    Role: specialiste nutrition sportive.
    On veut un plan JSON:
      {
        "plan_nutrition": {
          "kcal_jour": ...,
          "proteines_jour": ...,
          "lipides_jour": ...,
          "glucides_jour": ...,
          "aliments_proteines": [...],
          "aliments_lipides": [...],
          "aliments_glucides": [...]
        }
      }
    """
    prompt = f"""
    Tu es un specialiste de la nutrition sportive.
    Genere un plan nutritionnel au format JSON sans accents, 
    sans texte additionnel hors JSON.

    Champs obligatoires:
    - plan_nutrition.kcal_jour (int)
    - plan_nutrition.proteines_jour (int)
    - plan_nutrition.lipides_jour (int)
    - plan_nutrition.glucides_jour (int)
    - plan_nutrition.aliments_proteines (liste de string)
    - plan_nutrition.aliments_lipides (liste de string)
    - plan_nutrition.aliments_glucides (liste de string)

    Parametres:
      age: {data['age']}
      genre: {data['genre']}
      taille: {data['taille']}
      poids: {data['poids']}
      tour_bras: {data['tour_bras']}
      tour_cuisse: {data['tour_cuisse']}
      tour_hanche: {data['tour_hanche']}
      tour_nombril: {data['tour_nombril']}
      sport: {data['sport']}
      objectif: {data['objectif']}
      objectif_poids: {data['objectif_poids']}
      niveau: {data['niveau']}
      frequence: {data['frequence']}
      pas_semaine: {data['pas_semaine']}
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
    resp = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    if resp.status_code != 200:
        print("Erreur OpenAI (generate_nutrition_json):", resp.status_code, resp.text)
        return None

    try:
        rjson = resp.json()
        if "choices" not in rjson or not rjson["choices"]:
            return None
        content = rjson["choices"][0]["message"]["content"]
        cleaned = clean_json_response(content)
        return json.loads(cleaned)
    except:
        return None


def process_nutrition(data):
    """
    Genere le plan nutritionnel via ChatGPT. 
    On peut ensuite en faire un create_nutrition sur Bubble, etc.
    """
    nut_data = generate_nutrition_json(data)
    if not nut_data:
        return {"error": "Echec generation plan nutrition"}

    plan = nut_data["plan_nutrition"]

    # Exemple d'appel a Bubble si tu veux creer en base:
    # payload = {
    #     "kcal_jour": plan["kcal_jour"],
    #     "proteines_jour": plan["proteines_jour"],
    #     "lipides_jour": plan["lipides_jour"],
    #     "glucides_jour": plan["glucides_jour"],
    #     "aliments_proteines": plan["aliments_proteines"],
    #     "aliments_lipides": plan["aliments_lipides"],
    #     "aliments_glucides": plan["aliments_glucides"]
    # }
    # reponse_bubble = send_to_bubble("create_nutrition", payload)

    return {"message": "Plan nutrition genere avec succes!", "plan_nutrition": plan}


@app.route("/generate-nutrition", methods=["POST"])
def generate_nutrition():
    data = request.json
    result = process_nutrition(data)
    return jsonify(result), 201 if "message" in result else 500

# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
