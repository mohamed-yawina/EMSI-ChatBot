# Soutenance — EMSI-ChatBot V2

Support de présentation et de démonstration d’environ 6 minutes. Les résultats de recherche ou les pages cités pendant la démonstration doivent être ceux réellement affichés par l’application le jour J.

## Présentation orale (5 à 7 minutes)

### 0:00–0:40 — Présentation du besoin

Bonjour. Je présente EMSI-ChatBot, un assistant documentaire consacré à la brochure EMSI. Le but est de permettre à un étudiant ou à un candidat de poser des questions en langage naturel, de retrouver les passages utiles et de vérifier les réponses grâce aux références du document. Le projet ajoute également une recherche d’images dans la brochure et l’analyse d’images fournies par l’utilisateur.

### 0:40–1:30 — Architecture

L’interface est réalisée en Flutter pour le Web et Android. FastAPI reçoit les requêtes et orchestre les traitements. Qdrant stocke les vecteurs textuels et visuels dans deux collections. Les documents et les images extraits restent des données locales du projet ; ils ne sont pas reconstruits au démarrage.

Supabase fournit l’authentification, la base de données des conversations et le stockage privé des images téléversées. Groq fournit les appels cloud de génération textuelle et de Vision. Docker Compose facilite le lancement local de Qdrant, du backend et du client Web.

### 1:30–2:40 — Fonctionnement du RAG

Pour une question documentaire, BGE-M3 transforme la question en représentation numérique sur CPU. Le backend interroge Qdrant, puis combine les signaux sémantiques et lexicaux pour sélectionner des passages. Une sélection limitée de ces extraits est envoyée à Groq lorsque la génération est activée. L’historique sert à comprendre une question de suivi, mais ne constitue pas une preuve documentaire.

Les références PDF viennent des métadonnées des passages retrouvés. Le backend ne doit conserver que les sources qu’il peut vérifier. Si les documents récupérés ne répondent pas à la question, le chatbot doit signaler cette limite au lieu de compléter avec des connaissances générales.

Pour les images de la brochure, CLIP compare la question à des images déjà indexées dans Qdrant. CLIP aide au classement visuel, mais une similarité seule ne permet pas d’affirmer l’identité d’une personne ou le contenu précis d’une image. Une autre route analyse une image téléversée avec Groq Vision ; elle est distincte de CLIP et de la recherche dans la brochure.

### 2:40–5:30 — Scénario de démonstration

1. Ouvrir `http://localhost:8080`, montrer l’accueil et se connecter avec le compte de démonstration préparé.
2. Demander : **« Quels sont les campus EMSI mentionnés dans la brochure ? »** Montrer la réponse et les pages sources retournées.
3. Poser une question de suivi : **« Et celui de Rabat ? »**, puis **« Quelles formations y sont proposées ? »** Expliquer que la réponse doit distinguer les informations générales des preuves spécifiques au campus.
4. Activer explicitement la recherche d’images et demander un visuel de campus ou de laboratoire. Montrer la page associée, sans présenter une image non légendée comme une preuve certaine.
5. Dans une conversation authentifiée, téléverser une image de démonstration non sensible et demander : **« Que contient cette image ? »** Montrer la réponse Vision et le fait que la conversation peut être rouverte depuis l’historique.
6. Terminer par une question hors brochure, par exemple : **« Quelle est la météo à Rabat ? »** Montrer que le chatbot indique que cette information n’est pas disponible dans les documents EMSI.

Si un service externe est indisponible, ne pas simuler un résultat : expliquer la dépendance et montrer le flux automatisé ou un exemple préparé explicitement comme tel.

### 5:30–6:00 — Conclusion

Le projet associe recherche documentaire, génération contrôlée, citations, recherche d’images et gestion de conversations. Il sépare la récupération locale des documents et les appels cloud de génération. Les prochaines améliorations portent surtout sur l’évaluation systématique de la couverture documentaire, la validation des politiques Supabase sur un vrai projet et la préparation de sauvegardes avant tout déploiement partagé. Merci.

## Explication courte à dessiner au tableau

```text
Flutter Web / Android
  ├─ Supabase Auth et historique utilisateur
  └─ FastAPI
       ├─ question → BGE-M3 → Qdrant emsi_text → passages → Groq → réponse + citations
       ├─ demande d’image brochure → CLIP → Qdrant emsi_images → images locales + pages
       └─ image téléversée authentifiée → Supabase Storage privé → Groq Vision → message
```

Le backend vérifie les JWT pour les routes personnelles. Les opérations client sur les conversations sont régies par les politiques RLS ; les écritures privilégiées des messages assistant et le stockage privé passent par FastAPI. La clé `SUPABASE_SERVICE_ROLE_KEY` et les clés Groq restent dans l’environnement serveur.

## Questions possibles du jury

### Pourquoi utiliser un RAG plutôt qu’un chatbot général ?

Le RAG récupère des extraits de la brochure avant la génération. Cela rattache les réponses à une source définie et permet d’afficher des pages. Ce mécanisme réduit le risque d’invention, sans garantir une réponse parfaite.

### À quoi servent BGE-M3 et Qdrant ?

BGE-M3 encode la question et les passages pour la recherche sémantique. Qdrant stocke les vecteurs et renvoie les candidats. Le backend complète ce signal avec le classement lexical et les métadonnées documentaires.

### CLIP répond-il aux questions sur une image ?

Non. CLIP sert à retrouver des images indexées de la brochure à partir d’une description. Pour décrire une image téléversée, le projet appelle un modèle Vision Groq distinct.

### D’où viennent les citations ?

Des métadonnées `source` et `page` des passages Qdrant retenus. Le texte généré n’est pas autorisé à créer de nouvelles références. Une page citée reste à vérifier si l’extraction PDF a mélangé des colonnes.

### Comment sont traitées les questions de suivi ?

Flutter transmet un historique borné à cinq échanges. Le backend utilise cet historique pour reformuler la question de recherche et interpréter les références. Les réponses précédentes ne remplacent jamais les sources de la brochure.

### Comment les données des comptes sont-elles isolées ?

Supabase Auth fournit l’identité. FastAPI vérifie le JWT et la propriété de la conversation pour ses routes protégées ; les accès directs du client aux données persistées sont soumis à RLS. Les tests avec mocks ne prouvent pas à eux seuls l’isolation RLS réelle : celle-ci doit être vérifiée avec deux sessions non privilégiées sur le projet Supabase.

### Pourquoi certains premiers appels prennent-ils plus longtemps ?

Le premier appel peut charger les bibliothèques et les poids du modèle, absents du cache. Ensuite, le modèle textuel peut rester en mémoire si les contrôles RAM le permettent. Avant CLIP, BGE-M3 est libéré ; une recherche suivante peut donc entraîner un nouveau chargement. Les temps dépendent de la machine, du cache et du réseau.

### Le système fonctionne-t-il sans Internet ?

Pas complètement. Qdrant et les données locales sont sur la machine, mais la génération textuelle, Vision, Supabase Auth, l’historique et le stockage privé nécessitent les services configurés et un accès réseau.

### Quelles sont les limites principales ?

La couverture dépend de la brochure indexée et de la qualité de l’extraction PDF. Les réponses Vision peuvent mal interpréter une image. CLIP peut sélectionner un faux positif, donc ses scores ne sont pas des faits. Les services cloud ajoutent des dépendances réseau et de confidentialité. Les sauvegardes et l’exploitation de production demandent une configuration spécifique.

## Liste de contrôle avant la démonstration

- Vérifier `docker compose ps`, la santé de FastAPI et les collections Qdrant attendues.
- Vérifier que le navigateur charge Flutter Web et joint `FLUTTER_API_BASE_URL`.
- Vérifier les migrations Supabase, l’authentification, RLS et le bucket privé dans le projet utilisé.
- Vérifier la disponibilité des modèles Groq configurés sans afficher les clés.
- Préparer un compte de test et une image non sensible pour Vision.
- Conserver les journaux visibles, mais ne pas afficher les secrets, tokens, mots de passe ou URL signées.
- Éviter le premier chargement de modèle pendant la présentation : démarrer et préchauffer le système avant l’arrivée du jury.
- Garder une démonstration textuelle de repli si CLIP ou Vision n’est pas disponible ; annoncer clairement le repli.
- Ne pas lancer d’indexation ni de commande de suppression de volumes avant ou pendant la soutenance.
