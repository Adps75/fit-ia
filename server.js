const express = require("express");
const fetch = require("node-fetch");
require("dotenv").config();

const app = express();
app.use(express.json());

const FATSECRET_CLIENT_ID = process.env.FATSECRET_CLIENT_ID;
const FATSECRET_CLIENT_SECRET = process.env.FATSECRET_CLIENT_SECRET;

let accessToken = null;
let tokenExpiration = 0;

async function getAccessToken() {
  const now = Math.floor(Date.now() / 1000);

  if (accessToken && now < tokenExpiration) {
    return accessToken;
  }

  const credentials = Buffer.from(`${FATSECRET_CLIENT_ID}:${FATSECRET_CLIENT_SECRET}`).toString("base64");

  const response = await fetch("https://oauth.fatsecret.com/connect/token", {
    method: "POST",
    headers: {
      "Authorization": `Basic ${credentials}`,
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: "grant_type=client_credentials"
  });

  const data = await response.json();

  if (!data.access_token) {
    throw new Error("Erreur de récupération du Token");
  }

  accessToken = data.access_token;
  tokenExpiration = Math.floor(Date.now() / 1000) + data.expires_in - 60;

  return accessToken;
}

app.get("/search_food", async (req, res) => {
  try {
    const token = await getAccessToken();
    const searchTerm = req.query.food || "Poulet";

    let formData = new URLSearchParams();
    formData.append("method", "foods.search");
    formData.append("search_expression", searchTerm);
    formData.append("format", "json");

    const response = await fetch("https://platform.fatsecret.com/rest/server.api", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: formData
    });

    const data = await response.json();
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get("/get_food_details", async (req, res) => {
  try {
    const foodId = req.query.food_id; // Récupère l'ID de l'aliment depuis la requête
    if (!foodId) {
      return res.status(400).json({ error: "food_id is required" });
    }

    const token = await getAccessToken(); // Récupérer le token d'accès FatSecret

    let formData = new URLSearchParams();
    formData.append("method", "food.get.v4");
    formData.append("food_id", foodId);
    formData.append("format", "json");

    const response = await fetch("https://platform.fatsecret.com/rest/server.api", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: formData
    });

    const data = await response.json();
    res.json(data); // Retourne les détails de l'aliment
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});


const PORT = process.env.PORT || 3000; // Utilisation du port dynamique de Render
app.listen(PORT, () => console.log(`Serveur FatSecret Proxy en cours sur port ${PORT}`));
