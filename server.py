from flask import Flask, request, jsonify
import requests
import os
import json
import re

app = Flask(__name__)

# ---------------------------------------------------------
# Configuration ASCII ONLY (pas d'accents / emojis)
# ---------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

BUBBLE_BASE_URL = "https://fitia-47460.bubbleapps.io/version-test/api/1.1/wf/"
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY")
if not BUBBLE_API_KEY:
    raise ValueError("Missing BUBBLE_API_KEY")

def send_to_bubble(endpoint, payload):
    """
    Envoie les donnees a Bubble via workflows custom.
    """
    url = f"{BUBBLE_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }
    resp = requests.post(url, json=payload, headers=headers)
    print("-> Envoi a Bubble:", url)
    print("Payload:", json.dumps(payload, indent=2))
    print("Reponse code:", resp.status_code)
    print("Reponse text:", resp.text)
    if resp.status_code == 200:
        return resp.json()
    return None

def clean_json_response(response_text):
    """
    Retire les balises ```json ... ```
    """
    return re.sub(r"```json\s*(.*?)\s*```", r"\1", response_text, flags=re.DOTALL).strip()

# ---------------------------------------------------------
# 1) GENERATE TRAINING PROGRAM
# ---------------------------------------------------------

def generate_training_json(data):
    """
    Appelle OpenAI pour creer un plan d'entrainement JSON 
    (programme + cycles + duree + list_semaines + etc.).
    """
    prompt = f"""
    Tu es un coach expert en planification d'entrainements.
    Genere un programme d'entrainement EN JSON STRICTEMENT VALIDE,
    sans texte hors du JSON et sans accents.
    
    Important:
    - Cle 'duree' (int) pour le programme et pour chaque cycle
    - list_semaines[].numero, list_seances, etc.
    - Sur chaque exercice: list_series
    
    Parametres:
      Sport: {data['sport']}
      Niveau: {data['level']}
      Frequence: {data['frequency']} / semaine
      Objectif: {data['goal']}
      Genre: {data['genre']}
    """

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",   # ou "gpt-3.5-turbo" / "gpt-4" selon ton accès
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
    1) Appelle generate_training_json
    2) Recupere "programme" => cree/MAJ en base via Bubble
    3) Meme logique qu'avant: 
       - create_programme
       - create_cycle
       - create_semaine
       - create_seance
       - create_exercice
       - create_serie
       - update_exercice
       - update_seance
       - update_semaine
       - update_cycle
       - update_programme
    4) Renvoie {"message":"Programme cree avec succes!"}
    """

    prog_data = generate_training_json(data)
    if not prog_data:
        return {"error": "Echec generation programme"}

    # Lecture du JSON
    if "programme" not in prog_data:
        return {"error": "Aucune cle 'programme' dans la reponse GPT"}

    prog_obj = prog_data["programme"]
    # Champs programme
    prog_nom = prog_obj.get("nom", "Programme")
    prog_duree = prog_obj.get("duree", 12)

    # 1) On cree le Programme dans Bubble
    prog_payload = {
        "programme_nom": prog_nom,
        "programme_duree": prog_duree
    }
    # Optionnel: si "user_id" existe dans data
    if "user_id" in data:
        prog_payload["user_id"] = data["user_id"]

    resp_prog = send_to_bubble("create_programme", prog_payload)
    if not resp_prog or "response" not in resp_prog or "id" not in resp_prog["response"]:
        return {"error": "ID programme manquant (create_programme)"}
    programme_id = resp_prog["response"]["id"]

    list_cycles_ids = []

    # 2) Parcours des cycles
    list_cycles = prog_obj.get("list_cycles", [])
    for cycle_data in list_cycles:
        cycle_nom = cycle_data.get("nom", "Cycle")
        cycle_duree = cycle_data.get("duree", 1)

        cycle_resp = send_to_bubble("create_cycle", {
            "programme_id": programme_id,
            "cycle_nom": cycle_nom,
            "cycle_duree": cycle_duree
        })
        if not cycle_resp or "response" not in cycle_resp or "id" not in cycle_resp["response"]:
            continue
        cycle_id = cycle_resp["response"]["id"]
        list_cycles_ids.append(cycle_id)

        # Parcours des semaines
        list_semaines_ids = []
        for semaine_data in cycle_data.get("list_semaines", []):
            sem_num = semaine_data.get("numero", 1)
            sem_resp = send_to_bubble("create_semaine", {
                "cycle_id": cycle_id,
                "semaine_numero": sem_num
            })
            if not sem_resp or "response" not in sem_resp or "id" not in sem_resp["response"]:
                continue
            semaine_id = sem_resp["response"]["id"]
            list_semaines_ids.append(semaine_id)

            # Parcours des seances
            list_seances_ids = []
            for seance_data in semaine_data.get("list_seances", []):
                s_nom = seance_data.get("nom", f"Semaine {sem_num} - Seance")
                s_num = seance_data.get("numero", 1)

                seance_resp = send_to_bubble("create_seance", {
                    "semaine_id": semaine_id,
                    "seance_nom": s_nom,
                    "seance_numero": s_num
                })
                if not seance_resp or "response" not in seance_resp or "id" not in seance_resp["response"]:
                    continue
                seance_id = seance_resp["response"]["id"]
                list_seances_ids.append(seance_id)

                # Parcours des exercices
                list_exercices_ids = []
                for exo_data in seance_data.get("list_exercices", []):
                    exo_nom = exo_data.get("nom", "Exercice")
                    exo_tps = exo_data.get("temps_de_repos", 60)

                    exo_resp = send_to_bubble("create_exercice", {
                        "seance_id": seance_id,
                        "exercice_nom": exo_nom,
                        "exercice_temps_repos": exo_tps
                    })
                    if not exo_resp or "response" not in exo_resp or "id" not in exo_resp["response"]:
                        continue
                    exercice_id = exo_resp["response"]["id"]
                    list_exercices_ids.append(exercice_id)

                    # Parcours des series
                    list_series_ids = []
                    for serie_data in exo_data.get("list_series", []):
                        sets_count = serie_data.get("series", 1)
                        serie_charge = str(serie_data.get("charge", 0))
                        serie_reps = serie_data.get("repetitions", 0)
                        for i in range(sets_count):
                            serie_nom = f"Serie {i+1}"
                            s_resp2 = send_to_bubble("create_serie", {
                                "exercice_id": exercice_id,
                                "serie_nom": serie_nom,
                                "serie_charge": serie_charge,
                                "serie_repetitions": serie_reps,
                                "serie_nombre": 1
                            })
                            if s_resp2 and "response" in s_resp2 and "id" in s_resp2["response"]:
                                list_series_ids.append(s_resp2["response"]["id"])

                    # update_exercice (ajout des series)
                    if list_series_ids:
                        send_to_bubble("update_exercice", {
                            "id": exercice_id,
                            "list_series": list_series_ids
                        })

                # update_seance (ajout des exercices)
                if list_exercices_ids:
                    send_to_bubble("update_seance", {
                        "id": seance_id,
                        "list_exercices": list_exercices_ids
                    })

            # update_semaine (ajout des seances)
            if list_seances_ids:
                send_to_bubble("update_semaine", {
                    "id": semaine_id,
                    "list_seances": list_seances_ids
                })

        # update_cycle (ajout des semaines)
        if list_semaines_ids:
            send_to_bubble("update_cycle", {
                "id": cycle_id,
                "list_semaines": list_semaines_ids
            })

    # update_programme (ajout des cycles)
    if list_cycles_ids:
        send_to_bubble("update_programme", {
            "id": programme_id,
            "list_cycles": list_cycles_ids
        })

    return {"message": "Programme cree avec succes!"}


@app.route("/generate-program", methods=["POST"])
def generate_program():
    data = request.json
    result = process_training_program(data)
    return jsonify(result), 201 if "message" in result else 500

# ---------------------------------------------------------
# 2) GENERATE NUTRITION
# ---------------------------------------------------------

def generate_nutrition_json(data):
    """
    Rôle: specialiste nutrition sportive.
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
    Genere le plan nutritionnel + envoie a Bubble si besoin.
    """
    nut_data = generate_nutrition_json(data)
    if not nut_data:
        return {"error": "Echec generation plan nutrition"}

    plan = nut_data["plan_nutrition"]
    # on peut appeler send_to_bubble("create_nutrition", {...}) si on veut
    return {"message": "Plan nutrition genere avec succes!", "plan_nutrition": plan}

@app.route("/generate-nutrition", methods=["POST"])
def generate_nutrition():
    data = request.json
    result = process_nutrition(data)
    return jsonify(result), 201 if "message" in result else 500

# ---------------------------------------------------------
# 3) ANALYZE PROGRAM
# ---------------------------------------------------------

def analyze_program_gpt(data):
    prompt = f"""
    Tu es un coach expert. Analyse la semaine d'entrainement.
    Recois des donnees (charge, repetitions, etc.).
    Rends un JSON strict (sans accents) contenant les ajustements 
    a faire pour le programme. Ex:
    {{
      "update_programme": {{
        "cycles": [...],
        "commentaire": "..." 
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
        return None
    try:
        rjson = resp.json()
        if not rjson.get("choices"):
            return None
        content = rjson["choices"][0]["message"]["content"]
        cleaned = clean_json_response(content)
        return json.loads(cleaned)
    except:
        return None

def process_analyze_program(data):
    analyzed = analyze_program_gpt(data)
    if not analyzed:
        return {"error": "Echec analyze program"}
    # ex: updates = analyzed.get("update_programme", {})
    # send_to_bubble("update_programme", updates)
    return {"message": "Analyse programme OK", "update_programme": analyzed}

@app.route("/analyze-program", methods=["POST"])
def analyze_program():
    data = request.json
    result = process_analyze_program(data)
    return jsonify(result), 201 if "message" in result else 500

# ---------------------------------------------------------
# 4) ANALYZE NUTRITION
# ---------------------------------------------------------

def analyze_nutrition_gpt(data):
    prompt = f"""
    Tu es un specialiste nutrition sportive. 
    On te donne: ...
    Propose un update JSON ...
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role":"user","content":prompt}],
        "temperature": 0.7
    }
    resp = requests.post(OPENAI_ENDPOINT, json=payload, headers=headers)
    if resp.status_code != 200:
        return None
    try:
        rjson = resp.json()
        if not rjson.get("choices"):
            return None
        content = rjson["choices"][0]["message"]["content"]
        cleaned = clean_json_response(content)
        return json.loads(cleaned)
    except:
        return None

def process_analyze_nutrition(data):
    analysis = analyze_nutrition_gpt(data)
    if not analysis:
        return {"error":"Echec analyze nutrition"}
    return {"message":"Analyse nutrition OK","update_nutrition":analysis}

@app.route("/analyze-nutrition", methods=["POST"])
def analyze_nutrition():
    data = request.json
    result = process_analyze_nutrition(data)
    return jsonify(result), 201 if "message" in result else 500

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
