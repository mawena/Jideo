# Jideo — face swap local (photo + vidéo) — conception

Date : 2026-10-11
Statut : validé en conversation, en attente de relecture de la spec

## 1. Objectif

Jideo est une application d'IA auto-hébergée qui traite des photos et des
vidéos en local, exposée via une interface web sur le port **4545**. La
première version se limite au **face swap** : remplacer un ou plusieurs
visages d'une photo ou d'une vidéo cible par un visage source.

### Ce qui a été décidé

| Sujet | Décision |
|---|---|
| Positionnement | Outil Python **autonome**, sans dépendance à Marvis |
| Périmètre v1 | **Photo + vidéo** (MVP + V2 ci-dessous) |
| Installation | **Docker Compose**, script façade `./jideo` |
| Architecture | **Un seul conteneur**, worker intégré, file SQLite (approche 1) |
| Frontend | Vue 3 + Vite + Tailwind, compilé et servi par FastAPI |
| Matériel visé | **CPU uniquement** (pas de GPU NVIDIA sur la machine actuelle, 14 Go RAM) |

### Approches écartées

- **API + worker + Redis séparés** : plus robuste et extensible, mais aucun
  gain en CPU seul pour un usage personnel ; un seul swap vidéo sature déjà
  le CPU. Migration possible plus tard en remplaçant uniquement `jobs/`.
- **Gradio** : prototype très rapide, mais UX trop limitée (sélection du
  visage par clic, slider avant/après, historique) — réécriture inévitable.

## 2. Fonctionnalités

### Incluses en v1

Photo (MVP)
1. Upload drag & drop d'une image **source** et d'une image **cible**.
2. Détection automatique des visages de la cible, encadrés et numérotés.
3. Choix du ou des visages à remplacer (un, plusieurs, ou tous).
4. Swap via InsightFace `inswapper_128` (ONNX Runtime CPU).
5. Amélioration du visage GFPGAN (optionnelle, activée par défaut en photo).
6. Comparaison avant/après (slider) et téléchargement du résultat.
7. Historique local des traitements, avec suppression.

Vidéo (V2)
8. Upload d'une vidéo cible, traitement en arrière-plan avec progression
   (%, images/s, temps restant).
9. Aperçu sur une seule image avant le rendu complet.
10. Conservation de l'audio et des images par seconde d'origine.
11. Découpage : ne traiter qu'un segment `[début, fin]`.
12. Suivi du visage cible d'une image à l'autre par similarité d'embedding.
13. Annulation d'une tâche en cours ; relance d'une tâche échouée.

Garde-fous
- Accès limité à `127.0.0.1` par défaut, mot de passe obligatoire sinon.
- Marquage des résultats (métadonnée systématique, filigrane visible
  optionnel).
- Purge automatique des fichiers après N jours.

### Hors périmètre v1 (V3, plus tard)

14. Bibliothèque de visages sources nommés.
15. Plusieurs swaps simultanés (visage A → personne 1, visage B → personne 2).
16. Réglages avancés : opacité, adoucissement du masque, couleur de peau,
    masque de la bouche.
17. Traitement par lot d'un dossier d'images.

## 3. Architecture

```
jideo/
├── docker-compose.yml        # service unique "jideo", 127.0.0.1:4545 par défaut
├── Dockerfile                # python:3.12-slim + ffmpeg + onnxruntime (CPU)
├── .env.example
├── jideo                     # script : install / start / stop / restart / logs / shell / test
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI : monte l'API + sert le frontend compilé
│   │   ├── config.py         # chemins, limites, rétention, auth (depuis l'env)
│   │   ├── api/              # routes HTTP : media, faces, jobs, events (SSE)
│   │   ├── engine/           # cœur IA, sans aucune dépendance web ni disque
│   │   │   ├── models.py     # téléchargement + chargement des modèles ONNX
│   │   │   ├── detector.py   # détection + embeddings (InsightFace buffalo_l)
│   │   │   ├── swapper.py    # swap d'un visage sur une image (inswapper_128)
│   │   │   ├── enhancer.py   # GFPGAN v1.4 (ONNX)
│   │   │   ├── watermark.py  # filigrane visible + métadonnées
│   │   │   └── video.py      # flux ffmpeg → swap + suivi → encodage + audio
│   │   ├── jobs/             # file SQLite, worker unique, progression, annulation
│   │   ├── storage.py        # seul module qui touche data/
│   │   └── db.py             # SQLite : tables media, faces, jobs
│   ├── tests/
│   └── static/               # sortie du build frontend (non versionnée)
├── frontend/                 # Vue 3 + Vite + Tailwind
└── data/                     # volume Docker (non versionné)
    ├── uploads/  results/  models/  tmp/
    └── jideo.sqlite
```

### Responsabilités et frontières

- **`engine/`** : entrées/sorties = tableaux d'images (numpy BGR) et
  paramètres. Il ne connaît ni HTTP, ni SQLite, ni l'arborescence `data/`.
  Seule exception : `video.py` reçoit des chemins d'entrée/sortie et un
  callback de progression + un prédicat d'annulation, car ffmpeg travaille
  sur des fichiers. Testable et utilisable seul (CLI de debug).
- **`jobs/`** : prend la tâche suivante, appelle `engine`, publie la
  progression, gère l'annulation. **Une seule tâche à la fois.**
- **`storage.py`** : unique point d'accès disque (chemins, écriture
  atomique, suppression, purge, espace libre).
- **`api/`** : couche mince — validation, puis délégation à `storage` /
  `jobs` / `engine.detector`.

### Modèles

| Rôle | Modèle | Taille approx. |
|---|---|---|
| Détection + identité | InsightFace `buffalo_l` | ~280 Mo |
| Swap | `inswapper_128.onnx` | ~550 Mo |
| Amélioration | `GFPGANv1.4.onnx` | ~350 Mo |

Téléchargés une fois dans `data/models/` par `./jideo install` (sommes de
contrôle SHA-256 vérifiées), jamais embarqués dans l'image. Chargés une
seule fois au démarrage du worker et gardés en mémoire.

## 4. Flux de données

### 4.1 Médias et visages

1. `POST /api/media` (multipart) → validation (§5.1) → `storage` écrit le
   fichier → analyse immédiate (hors file) :
   - photo : dimensions ;
   - vidéo : ffprobe (durée, fps, résolution, présence d'audio) + miniature.
   Réponse : `{id, kind: "photo"|"video", width, height, duration?, fps?, has_audio?, thumbnail_url}`.
2. `POST /api/media/{id}/faces?t=<secondes>` → détection synchrone (~0,3 s)
   sur la photo ou sur l'image à l'instant `t` de la vidéo. Les embeddings
   sont conservés côté serveur (table `faces`), le client reçoit
   `[{face_id, index, bbox: [x1,y1,x2,y2], score}]`.
3. L'utilisateur clique sur les cadres pour choisir le visage source et les
   visages cibles.

Autres routes : `GET /api/media/{id}/file`, `DELETE /api/media/{id}`.

### 4.2 Tâche photo

`POST /api/jobs`
```json
{
  "type": "photo",
  "source_face_id": "…",
  "target_media_id": "…",
  "target_face_ids": ["…"],          // ou "all"
  "enhance": true,
  "watermark": true
}
```
Worker : chargement cible → pour chaque visage cible : swap avec
l'embedding source → GFPGAN si demandé → marquage → écriture dans
`data/results/` → événement `done`. Passe par la file comme tout le reste
(un seul chemin de code) ; la file étant presque toujours vide, le résultat
arrive en 1–3 s.

### 4.3 Aperçu vidéo

`type: "preview"` avec `target_media_id` vidéo et `t`. Même pipeline que la
photo sur une image extraite. **Priorité haute** : passe devant les tâches
vidéo en attente (pas devant celle en cours).

### 4.4 Tâche vidéo

```json
{
  "type": "video",
  "source_face_id": "…",
  "target_media_id": "…",
  "target_face_ids": ["…"],          // visages choisis sur l'image de référence
  "trim": {"start": 10.0, "end": 25.0},
  "enhance": false,
  "downscale_720p": false,
  "similarity_threshold": 0.35,
  "watermark": true
}
```
Worker :
1. `ffmpeg` décode le segment en flux brut (`rawvideo bgr24` sur stdout) —
   aucune image intermédiaire sur disque.
2. Pour chaque image : détection → on garde les visages dont la similarité
   cosinus avec un des embeddings cibles ≥ `similarity_threshold` → swap →
   GFPGAN si demandé → filigrane → écriture sur stdin d'un second `ffmpeg`
   (H.264, `yuv420p`, CRF 18, fps d'origine) dans `data/tmp/`.
3. Mux final : vidéo produite + piste audio d'origine sur le même segment
   (`-ss/-to`, `-c:a copy`, repli sur ré-encodage AAC si la copie échoue),
   métadonnée `comment`, puis déplacement atomique vers `data/results/`.
4. Progression publiée toutes les ~10 images :
   `{progress, fps, eta_s, frames_done, frames_total}`.
5. Annulation : drapeau vérifié à chaque image → arrêt des deux processus
   ffmpeg → suppression des fichiers partiels → statut `cancelled`.
6. Statistique de suivi : pourcentage d'images où le visage cible a été
   trouvé, enregistré sur la tâche.

### 4.5 Événements et historique

- `GET /api/events` : flux **SSE** unique (`queued`, `started`, `progress`,
  `done`, `failed`, `cancelled`), payload `{job_id, …}`.
- `GET /api/jobs` (historique paginé), `GET /api/jobs/{id}`,
  `POST /api/jobs/{id}/cancel`, `POST /api/jobs/{id}/retry`
  (crée une nouvelle tâche avec les mêmes paramètres),
  `DELETE /api/jobs/{id}` (supprime aussi le résultat),
  `GET /api/jobs/{id}/result`.

### 4.6 Performances attendues (CPU)

- Photo : 1–3 s (avec GFPGAN).
- Vidéo : ~1–2 images/s sans amélioration, ~0,3–0,5 avec. Ex. 30 s à
  30 fps (900 images) ≈ 8–15 min sans, 30–50 min avec.
- Par défaut en vidéo : amélioration **désactivée** ; option « réduire à
  720p » proposée pour les sources de plus haute résolution.

## 5. Erreurs, limites et garde-fous

### 5.1 Validation des uploads

- Formats : photo `jpg/png/webp`, vidéo `mp4/mov/webm/mkv`. Type vérifié par
  Pillow / ffprobe, pas par l'extension.
- Limites configurables (`.env`) :
  - `JIDEO_MAX_PHOTO_MB=25`
  - `JIDEO_MAX_VIDEO_MB=1024`
  - `JIDEO_MAX_VIDEO_SECONDS=300` (s'applique à la durée **traitée**, donc
    après découpage)
  - photos redimensionnées au-delà de 4096 px de côté.
- Rejets → HTTP 413 / 415 / 422 avec message lisible en français.

### 5.2 Erreurs métier

| Situation | Comportement |
|---|---|
| Aucun visage dans la source | 422 « Aucun visage détecté dans l'image source » |
| Plusieurs visages dans la source | l'UI impose un choix explicite, jamais de sélection silencieuse |
| Aucun visage dans une photo cible | 422 |
| Image vidéo sans visage correspondant | image conservée telle quelle |
| Suivi faible sur une vidéo | tâche `done` avec avertissement « visage trouvé sur X % des images » (affiché si X < 50) |
| Modèles absents | le serveur démarre, l'UI affiche « lancez `./jideo install` », les tâches sont refusées (503) |

### 5.3 Robustesse du worker

- Exception dans une tâche → `failed` + message en base, stack trace dans
  les logs ; le worker continue.
- Au démarrage : tâches `running` → `failed` (« interrompue ») ; `data/tmp/`
  vidé.
- `data/tmp/` nettoyé en fin de chaque tâche, quel que soit le statut.
- Espace libre < 2 Go → refus de démarrer une tâche vidéo (`failed`,
  message explicite).

### 5.4 Garde-fous

1. **Accès** : `JIDEO_BIND=127.0.0.1` par défaut. Toute autre valeur exige
   `JIDEO_PASSWORD`, sinon le serveur refuse de démarrer. Auth par session
   (cookie signé `JIDEO_SECRET`), page de connexion simple.
2. **Marquage** : métadonnée « Généré par IA — Jideo » toujours écrite
   (EXIF `ImageDescription` + XMP pour les photos, `comment` pour le MP4) ;
   filigrane visible discret « Jideo » en bas à droite, **activé par
   défaut**, désactivable par tâche.
3. **Purge** : tâche périodique (au démarrage puis toutes les 6 h) qui
   supprime médias et résultats plus vieux que `JIDEO_RETENTION_DAYS=30`
   (`0` = jamais).
4. **Confidentialité** : aucun appel réseau sortant hors téléchargement des
   modèles à l'installation ; pas de télémétrie.

## 6. Interface

Page unique, deux zones :

- **Atelier** : dépôt source + dépôt cible ; cadres cliquables sur les
  visages détectés ; pour une vidéo, lecteur avec curseur temporel pour
  choisir l'image de référence et les bornes du découpage ; options
  (amélioration, 720p, filigrane, seuil de similarité en « avancé ») ;
  boutons « Aperçu » (vidéo) et « Lancer ».
- **Historique** : liste des tâches avec statut en direct (SSE), barre de
  progression + temps restant, actions annuler / relancer / supprimer /
  télécharger ; vue résultat avec slider avant/après (photo) ou lecteur
  (vidéo).

## 7. Tests

`./jideo test` exécute pytest dans le conteneur.

| Niveau | Portée | Moyen |
|---|---|---|
| Moteur | détection, swap, suivi, pipeline vidéo, audio | fixtures libres de droits dans `tests/fixtures/` (quelques photos, vidéo de 2 s avec audio) ; vérifie nombre de visages, similarité du visage swappé avec la source, dimensions/fps/audio du résultat |
| File | ordre, priorité aperçu, annulation, reprise après redémarrage, nettoyage `tmp` | moteur factice |
| API | uploads valides/invalides, 413/415/422/503, auth obligatoire hors localhost | `TestClient` FastAPI |
| E2E | parcours photo + aperçu vidéo | Playwright, un seul scénario |

Les tests utilisant les vrais modèles sont marqués `slow` et ignorés si
`data/models/` est incomplet.

## 8. Étapes de livraison

1. **Socle** : Dockerfile, compose, `./jideo`, FastAPI sur 4545, SQLite,
   `storage`, téléchargement des modèles.
2. **Moteur photo** : détection, swap, GFPGAN, marquage (+ CLI de debug).
3. **File + API** : media, faces, jobs, SSE.
4. **UI photo** : upload, sélection par clic, avant/après, historique →
   **MVP**.
5. **Moteur vidéo** : flux ffmpeg, suivi, audio, découpage, 720p.
6. **UI vidéo** : aperçu, progression/ETA, annulation/relance → **V2**.
7. **Garde-fous + finitions** : auth, purge, contrôle disque, test E2E.

## 9. Risques et points d'attention

- **Licences des modèles** : `inswapper_128` et `buffalo_l` (InsightFace)
  sont distribués pour un usage **non commercial** uniquement. Acceptable
  pour un usage personnel ; à réévaluer avant toute utilisation commerciale.
- **Sources des modèles** : `inswapper_128.onnx` n'est plus publié
  officiellement ; les URLs de téléchargement (miroirs) et leurs SHA-256
  seront figés dans `engine/models.py`. GFPGAN en ONNX provient d'une
  conversion communautaire — même traitement.
- **Qualité** : le swap travaille à 128 px ; sans amélioration, les gros
  plans en haute résolution sont flous. C'est la raison du GFPGAN
  optionnel et de l'option 720p.
- **Performances CPU** : voir §4.6 ; un passage au GPU plus tard ne
  changerait que l'image Docker (`onnxruntime-gpu`) et le provider ONNX.
