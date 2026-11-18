# Client Flutter EMSI-ChatBot

Ce package contient le client Flutter Web/Android. Pour l’installation complète de Qdrant et FastAPI, voir [le guide Windows](../docs/INSTALLATION_WINDOWS.md) et le [README principal](../README.md).

Depuis ce dossier :

```powershell
flutter pub get
flutter analyze
flutter test
```

L’URL FastAPI peut être fournie au build via `API_BASE_URL`. Exemple Web sur le même PC :

```powershell
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Pour Android Emulator standard, utiliser `http://10.0.2.2:8000`. Le client ne contient pas de clé Groq. Il conserve les cinq derniers échanges côté interface et les transmet à `POST /api/chat`; « Nouvelle conversation » les efface. La recherche d’images est facultative et désactivée au démarrage.
