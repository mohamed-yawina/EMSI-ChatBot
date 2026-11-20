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
flutter run -d chrome --web-port 5000 `
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=SUPABASE_URL=https://<project-ref>.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=<publishable-client-key>
```

### Émulateur Android standard

```powershell
flutter run -d <deviceId> `
  --dart-define=API_BASE_URL=http://10.0.2.2:8000 `
  --dart-define=SUPABASE_URL=https://<project-ref>.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=<publishable-client-key>
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

## Conversations persistantes Supabase (Mission 20)

La persistance n'est activée qu'après l'application manuelle de `supabase/migrations/20261118_mission20_conversations.sql`. Consultez [docs/MISSION20_SUPABASE_SETUP.md](MISSION20_SUPABASE_SETUP.md) pour revoir le schéma, les politiques RLS, les contrôles SQL, le scénario à deux comptes et les limites de confiance. La migration n'a pas été exécutée automatiquement.

Ajoutez dans le `.env` à la racine du dépôt `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` et `SUPABASE_SERVICE_ROLE_KEY`. La clé service_role est réservée au serveur FastAPI. Ne la passez jamais à Flutter, ni avec `--dart-define`, ni dans un fichier de configuration mobile.

Après migration/configuration, lancez Flutter depuis `mobile` avec les deux paramètres clients :

```powershell
Set-Location .\mobile
flutter run -d chrome --web-port 5000 `
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=SUPABASE_URL=https://<project-ref>.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=<publishable-client-key>
```

Le script réel RLS (non privilégié) se lance depuis la racine avec `.\supabase\scripts\test_rls.ps1`; il exige deux comptes de test confirmés et supprime la conversation de test créée par le compte A.

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

## Configuration Supabase Auth (Mission 19)

Dans le tableau de bord Supabase :

1. Ouvrez **Authentication → Sign In / Providers**, activez le fournisseur e-mail et gardez la confirmation d'adresse activée.
2. Dans **Authentication → URL Configuration**, ajoutez l'origine Web locale réellement utilisée (par exemple `http://localhost:5000`) à la liste des redirections. Ajoutez également `com.emsi.chatbot://login-callback/` pour Android. En production, configurez seulement les origines HTTPS que vous contrôlez.
3. Dans les paramètres de signature JWT, activez une clé asymétrique ES256 ou RS256. Le backend valide via le JWKS public du projet et rejette HS256, car sa clé symétrique n'est pas publiée dans JWKS.
4. Récupérez l'URL du projet et la clé **publishable**. N'utilisez jamais `service_role` ou une clé secrète dans Flutter.

Ajoutez `SUPABASE_URL` dans le `.env` local à la racine (copiez d'abord `.env.example`). Flutter ne lit pas ce fichier : transmettez les valeurs de configuration au lancement avec Dart defines. Depuis `mobile/`, remplacez les valeurs d'exemple :

```powershell
flutter pub get
flutter run -d chrome --web-port 5000 `
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=SUPABASE_URL=https://your-project-ref.supabase.co `
  --dart-define=SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_project_key
```

Pour un émulateur Android standard, remplacez `API_BASE_URL` par `http://10.0.2.2:8000` et utilisez `flutter run -d <deviceId>`. L'URI de retour configurée dans l'app Android est `com.emsi.chatbot://login-callback/`.

Le formulaire d'inscription doit afficher une demande de confirmation ; ouvrez le lien dans l'origine Web ou Android autorisée, puis connectez-vous. La récupération du mot de passe utilise le même mécanisme de redirection et ouvre le formulaire de nouveau mot de passe. Le backend `GET /api/users/me` requiert un bearer token et le valide par JWKS. `POST /api/chat` reste anonyme pour compatibilité V1 ; ne l'exposez pas publiquement sans renforcer cette politique.

Les tests automatisés utilisent des JWT de test et des JWKS simulés. Ils ne prouvent pas qu'un projet Supabase réel, ses e-mails, SMTP, redirections ou sa clé de signature fonctionnent. Validez ces étapes avec un compte de test dédié avant une démonstration. Ne placez aucun vrai secret dans Git ou une capture d'écran.
