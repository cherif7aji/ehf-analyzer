#!/bin/bash

# Script de mise à jour automatique depuis Git
set -e

echo "🔄 Mise à jour de l'Analyseur EHF depuis Git"
echo "==========================================="

# Récupérer les dernières modifications
echo "📥 Récupération des modifications..."
git pull origin main

# Redéployer l'application
echo "🚀 Redéploiement de l'application..."
./deploy.sh

echo "✅ Mise à jour terminée!"
