# Installation et lancement sous Windows

Ce guide démarre Qdrant dans Docker, l’API FastAPI dans le venv Python du projet et le client Flutter séparément. Il ne réindexe pas les collections.

## Prérequis

- Windows 11 et PowerShell.
- Python 3.11 disponible via `py -3.11`.
- Docker Desktop avec Docker Compose v2, démarré avant les commandes Docker.
- Flutter SDK. Android Studio et un appareil/émulateur sont nécessaires uniquement pour Android.
- Accès réseau pour Groq Cloud et, si les poids ne sont pas déjà en cache, pour télécharger BGE-M3/CLIP au premier besoin.
- Une clé Groq et un identifiant de modèle actif si l’application doit générer des réponses (`use_llm=true`).

## 1. Préparer les variables Groq

Depuis la racine `EMSI-ChatBot` :

```powershell
Copy-Item .env.example .env
notepad .env
```

Renseigner `GROQ_API_KEY` et `GROQ_MODEL` dans le fichier local. Le modèle n’est pas imposé par le code. Ne copiez pas la clé dans une commande PowerShell enregistrée, Flutter ou une capture d’écran.

## 2. Démarrer Qdrant

```powershell
docker compose up -d qdrant
docker compose ps
Invoke-RestMethod http://127.0.0.1:6333/collections
```

Le script backend attend les collections `emsi_text` et `emsi_images`. Si elles sont absentes, il s’arrête avec un message d’aide ; il ne crée ni ne remplit les collections. Le volume Docker `qdrant_storage` persiste lors des redémarrages ordinaires de conteneur. Ne lancez pas les scripts `backend/scripts/index_qdrant.py`, `embed_text.py` ou `embed_images.py` pour une simple démonstration.

## 3. Installer les dépendances Backend une première fois

Si le venv n’existe pas encore :

```powershell
py -3.11 --version
py -3.11 -m venv backend\.venv
& .\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

Cette installation n’installe pas Python lui-même. Elle peut être longue ; `sentence-transformers` apporte PyTorch et ses dépendances. Les poids Hugging Face sont téléchargés au premier chargement requis si le cache local ne les contient pas. Ne lancez pas les deux modèles en parallèle.

Si le venv existant pointe vers un runtime Python supprimé/déplacé, vérifiez d’abord `backend\.venv\pyvenv.cfg`. Reconstruisez uniquement ce venv si vous avez confirmé que Python 3.11 est installé :

```powershell
py -3.11 -m venv backend\.venv --clear
& .\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

## 4. Démarrer FastAPI

Depuis la racine du projet :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\backend\start_backend.ps1
```

Le script vérifie Qdrant, les collections attendues et le venv, puis lance Uvicorn sur le port `8000`. Gardez la fenêtre ouverte. Dans une seconde fenêtre :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

La réponse `{ status: "ok" }` confirme seulement qu’HTTP répond ; elle ne prouve pas la disponibilité de Groq ou la réussite d’une recherche Qdrant. `/docs` expose le schéma OpenAPI.

## 5. Démarrer Flutter

Depuis la racine :

```powershell
Set-Location .\mobile
flutter pub get
flutter devices
```

### Flutter Web / Chrome sur le même PC

```powershell
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

### Émulateur Android standard

```powershell
flutter run -d <deviceId> --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` est l’adresse de l’hôte depuis l’émulateur Android Studio standard.

### Téléphone Android sur le réseau local

Trouver l’IPv4 du PC avec `ipconfig`, puis lancer :

```powershell
flutter run -d <deviceId> --dart-define=API_BASE_URL=http://<IP-LAN-DU-PC>:8000
```

Uvicorn écoute sur `0.0.0.0` pour ce cas. Autorisez le port uniquement sur un profil de pare-feu privé et réseau de confiance. Ne publiez pas l’API ni Qdrant sur Internet. Les builds Android doivent autoriser le trafic HTTP clair vers l’API locale ; cette configuration dépend de la cible et du mode de build.

## Validation légère

Backend (les tests existants sont mockés et ne doivent pas charger BGE-M3/CLIP) :

```powershell
& .\backend\.venv\Scripts\python.exe -m pip install pytest
& .\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

`pytest` est une dépendance de développement, pas nécessaire au démarrage normal de l’API.

Flutter, depuis `mobile` :

```powershell
flutter analyze
flutter test
```

Test manuel de contrat sans RAG lourd, une fois FastAPI démarré :

```powershell
$body = @{ question = 'Question de démonstration'; use_llm = $false; include_images = $false; history = @() } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/chat' -ContentType 'application/json; charset=utf-8' -Body $body
```

Pour tester réellement le RAG/Groq, utiliser Flutter ou `/api/chat` avec `use_llm=true`; cela peut charger BGE-M3. Pour vérifier CLIP, activer explicitement les images dans l’interface uniquement si la machine dispose de suffisamment de mémoire disponible.

## Arrêt et dépannage

- Arrêter Flutter et FastAPI avec `Ctrl+C` dans leurs fenêtres.
- Arrêter le conteneur sans supprimer le volume : `docker compose stop qdrant`.
- Consulter `docker compose logs qdrant` si le service ne démarre pas.
- Si `backend\.venv\Scripts\python.exe` indique que son Python de base n’existe plus, utiliser la procédure de reconstruction ci-dessus ; ne réinstallez pas Python sans nécessité.
- Si le backend signale des collections manquantes, arrêtez-vous : la présente procédure ne réindexe pas les données.
- Si Flutter ne joint pas FastAPI, vérifier l’URL `API_BASE_URL`, le port `8000`, le pare-feu privé et l’adresse de passerelle de la cible.
