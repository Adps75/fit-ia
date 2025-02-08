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

app.listen(3000, () => console.log("Serveur FatSecret Proxy en cours sur port 3000"));
