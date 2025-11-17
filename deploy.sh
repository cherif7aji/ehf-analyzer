#!/bin/bash

# Script de déploiement et mise à jour pour l'Analyseur EHF
set -e

echo "🚀 Déploiement/Mise à jour de l'Analyseur EHF"
echo "============================================="

# Arrêter les conteneurs existants
echo "🛑 Arrêt des conteneurs existants..."
docker-compose down 2>/dev/null || true

# Nettoyer les images non utilisées
echo "🧹 Nettoyage des images..."
docker system prune -f

# Construire et lancer
echo "🔨 Construction de l'image..."
docker-compose build --no-cache

echo "🚀 Lancement de l'application..."
docker-compose up -d

# Attendre que l'application soit prête
echo "⏳ Attente du démarrage..."
sleep 10

echo "✅ Application mise à jour et déployée!"
echo "🌐 Accès: http://localhost:1000"
