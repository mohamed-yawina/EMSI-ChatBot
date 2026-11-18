# Démonstration académique EMSI-ChatBot

Durée proposée : **7 à 9 minutes**. Préparer Docker/Qdrant et FastAPI avant l’arrivée du public pour ne pas consacrer la démonstration au premier démarrage des modèles.

## Présentation

EMSI-ChatBot est un prototype qui répond à des questions sur la brochure EMSI. Il recherche d’abord des passages dans Qdrant avec BGE-M3, puis peut utiliser Groq Cloud pour rédiger une réponse ancrée dans ces passages. Les sources retournées reprennent les pages PDF enregistrées dans les métadonnées. La recherche d’images CLIP est disponible à la demande.

## Architecture à présenter

```text
Flutter Web/Android → FastAPI → BGE-M3 → Qdrant (emsi_text)
                                  ├→ Groq Cloud (réponse et citations vérifiées)
                                  └→ CLIP, si demandé → Qdrant (emsi_images)
```

- BGE-M3 effectue la recherche textuelle sur CPU.
- Qdrant conserve les vecteurs et les métadonnées source/page.
- Groq reçoit la question, les passages utiles sélectionnés et l’historique récent borné lorsqu’il existe.
- CLIP classe des images déjà indexées ; il n’est pas activé par défaut.
- Aucun de ces composants ne remplace la brochure comme source documentaire.

## Préparation avant le passage

1. Vérifier que Docker Desktop fonctionne et que les collections Qdrant existent.
2. Démarrer FastAPI et contrôler `/health`.
3. Ouvrir Flutter Web ou l’application Android sur le réseau local.
4. Vérifier que `GROQ_API_KEY` est configurée localement, sans la projeter ou l’afficher.
5. Pour montrer CLIP, commencer avec la recherche d’images désactivée ; ne l’activer que si la machine reste stable et si les contrôles RAM du backend l’autorisent.
6. Ouvrir la brochure PDF séparément pour pouvoir vérifier une page réellement citée.

## Déroulé suggéré (7–9 minutes)

### 0:00–1:00 — But et interface

Présenter le problème : retrouver une information dans une brochure sans parcourir toutes ses pages. Montrer l’écran d’accueil, les suggestions, le thème et les panneaux responsifs sans détailler les dépendances.

### 1:00–3:00 — Recherche documentaire et citation

Envoyer une question générale, par exemple :

> Quels campus EMSI sont mentionnés dans la brochure ?

Montrer la réponse et ses références sous le message. Ouvrir ensuite dans le PDF la page effectivement retournée par l’API. La page dépend du résultat réellement récupéré ; ne pas annoncer à l’avance un numéro non vérifié.

### 3:00–5:00 — Suivi conversationnel et prudence documentaire

Dans la même conversation, demander :

> Et celui de Rabat ?

Puis :

> Quelles formations y sont proposées ?

Expliquer que l’historique aide à interpréter « y », mais ne sert pas de preuve. Si les passages ne relient pas explicitement une formation au campus de Rabat, l’application doit signaler cette limite et ne pas présenter la liste générale comme une offre locale. Utiliser « Nouvelle conversation » pour montrer la remise à zéro.

### 5:00–6:30 — Recherche d’images facultative

Activer la case **Recherche d’images**, puis demander :

> Montre-moi des images associées aux campus EMSI.

Présenter les images renvoyées et leurs métadonnées de source/page si elles s’affichent. CLIP est conditionnel : le backend confirme la libération de BGE-M3 et la RAM disponible avant de le lancer. Si ces contrôles reportent la recherche ou si aucune image n’est retournée, expliquer que la réponse textuelle reste disponible.

### 6:30–7:30 — Question hors brochure

Demander :

> Quelle sera la météo demain à Casablanca ?

La brochure ne contient pas nécessairement cette information ; l’assistant doit dire qu’il ne l’a pas trouvée dans les documents EMSI disponibles plutôt que d’inventer une réponse.

### 7:30–9:00 — Limites et conclusion

Résumer les protections et limites : sources limitées au corpus retrouvé, citations à vérifier dans le PDF, latence variable au premier chargement, génération Groq via Internet, images facultatives et contrôle mémoire. Préciser que le prototype n’est pas un système d’information officiel ni un moteur de recherche général.

## Exemple de forme de citation

La référence visible doit être lue telle que renvoyée par l’API, par exemple :

```text
Brochure-EMSI.pdf · page <numéro retourné par FastAPI>
```

Le numéro entre chevrons est un espace réservé pour la démonstration : le remplacer uniquement par le numéro réellement retourné, puis vérifier la page correspondante dans le PDF. Ne pas inventer d’URL ni de référence.

## Comment parler des performances

Les logs backend enregistrent séparément les durées de recherche et de génération ainsi que la durée totale. Le premier appel peut être ralenti par l’initialisation et le chargement des poids ; une recherche persistante BGE-M3 peut réduire le coût des questions suivantes si le seuil RAM est respecté. CLIP peut avoir son propre coût de démarrage lorsqu’il est activé.

Aucun benchmark comparatif n’a été exécuté pour ce guide. Si vous citez des nombres, notez avant la démonstration la machine, l’état froid/chaud des modèles, l’option images et les temps observés pendant cette session. Ne comparez pas des mesures faites dans des conditions différentes comme s’il s’agissait d’un benchmark contrôlé.

## Conclusion orale possible

> « EMSI-ChatBot associe la recherche sémantique à des réponses sourcées dans la brochure. Les citations visibles permettent de revenir au document, la mémoire sert uniquement à comprendre les questions de suivi, et la recherche d’images reste facultative afin de préserver les ressources de la machine. »
