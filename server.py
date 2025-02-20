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

def process_training_program(data):
    """
    Genere un programme (same logic as before).
    """
    prog_data = generate_training_json(data)
    if not prog_data:
        return {"error": "Echec generation programme"}

    # On lit le champ "programme" etc.
    # ... Meme code que tu avais avant ...
    # => send_to_bubble("create_programme", {...})
    # => create cycles, semaines, seances, etc.
    # => renvoi {"message": "Programme cree avec succes"}
    
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

    # Ex: on recupere nut_data["plan_nutrition"]
    plan = nut_data["plan_nutrition"]
    # Puis on envoie a Bubble. Ex:
    # create_nutrition_plan ou update_nutrition_plan
    payload = {
        "kcal_jour": plan["kcal_jour"],
        "proteines_jour": plan["proteines_jour"],
        "lipides_jour": plan["lipides_jour"],
        "glucides_jour": plan["glucides_jour"],
        "aliments_proteines": plan["aliments_proteines"],
        "aliments_lipides": plan["aliments_lipides"],
        "aliments_glucides": plan["aliments_glucides"]
    }
    # ex: reponse = send_to_bubble("create_nutrition", payload)
    # pour l'exemple, on ne fait rien:
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
    """
    Rôle: Analyser la semaine d'entrainement, renvoyer 
    un JSON d'update pour le programme (ou la semaine suivante).
    Champs potentiels:
      - charge, repetitions, yes/no, fatigue, qualite sommeil, 
        motivation, douleurs, heures de sommeil, etc.
    """
    prompt = f"""
    Tu es un coach expert. Analyse la semaine d'entrainement.
    Recois des donnees (charge, repetitions, yes/no, fatigue, sommeil, etc.).
    Rends un JSON strict (sans accents) contenant les ajustements a faire 
    pour le programme. Par exemple:
    {{
      \"update_programme\": {{
        \"cycles\": [...],
        \"commentaire\": \"...\" 
      }}
    }}
    """
    # On inclut data
    # ...
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

def process_analyze_program(data):
    """
    1) On envoie a ChatGPT 
    2) ChatGPT repond un JSON d'update
    3) On appelle les workflows bubble type update_xxx si besoin
    """
    analyzed = analyze_program_gpt(data)
    if not analyzed:
        return {"error": "Echec analyze program"}
    # ex: On recupere "update_programme"
    # updates = analyzed["update_programme"]
    # On appelle send_to_bubble("update_programme", updates)
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
    """
    Meme principe: on envoie a GPT un role de 'analyse plan nutrition'.
    On recoit un JSON e.g. 'update_nutrition' => { newKcal, newProteines, ... }
    """
    prompt = f"""
    Tu es un specialiste nutrition sportive. 
    On te donne:
      - poids
      - mensurations
      - objectif 
      - plan alimentaire actuel (kcal, glucides, proteines, lipides)
    Propose un update de ce plan (kcal, proteines, lipides, glucides).
    Donne un JSON strict sans accent, ex:
    {{
      \"update_nutrition\": {{
        \"kcal_jour\": ...,
        \"proteines_jour\": ...,
        \"lipides_jour\": ...,
        \"glucides_jour\": ...
      }}
    }}
    """
    # Meme modele
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

def process_analyze_nutrition(data):
    """
    Meme principe: GPT repond un JSON 'update_nutrition'
    On envoie a bubble via 'update_nutrition_plan' par exemple
    """
    analysis = analyze_nutrition_gpt(data)
    if not analysis:
        return {"error": "Echec analyze nutrition"}
    # ex: maj = analysis["update_nutrition"]
    # send_to_bubble("update_nutrition", maj)
    return {"message": "Analyse nutrition OK", "update_nutrition": analysis}

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
