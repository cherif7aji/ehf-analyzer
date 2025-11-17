# Analyseur EHF - Déploiement Git + Docker

## 🚀 Installation initiale sur VPS

### 1. Cloner le projet
```bash
git clone [URL_DE_VOTRE_REPO] ehf-analyzer
cd ehf-analyzer
```

### 2. Déployer
```bash
./deploy.sh
```

### 3. Configurer Nginx
```bash
# Copier la config Nginx
sudo cp nginx-config.txt /etc/nginx/sites-available/ehf-analyzer

# Modifier le domaine dans le fichier
sudo nano /etc/nginx/sites-available/ehf-analyzer

# Activer le site
sudo ln -s /etc/nginx/sites-available/ehf-analyzer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 🔄 Mise à jour après modifications

```bash
./update.sh
```

Cette commande fait automatiquement :
- `git pull` pour récupérer les modifications
- Reconstruction et redéploiement de l'application

## 🌐 Accès

- **Avec Nginx :** http://votre-domaine.com
- **Direct :** http://IP_VPS:1000
