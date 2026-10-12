# Journal d'exécution — décisions (Ruling) et points mineurs reportés

Spec: docs/superpowers/specs/2026-10-11-jideo-faceswap-design.md (reachable, binding)
Branch: feat/jideo-v1 (from main @ 2476387)

Ruling: travailler sur une branche feat/jideo-v1 dans le dépôt principal plutôt qu'un worktree — dépôt neuf, sans autre travail en cours, et docker-compose monte ./data relatif au checkout (les modèles ~1,2 Go seraient sinon dupliqués) — coût si faux : aucun, la branche se fusionne ou se jette.

## Pre-flight scan

| Paire / tâche | Produit → consommé | Constat |
|---|---|---|
| T1 → T2..T14 | Settings, create_app, fixture settings, ./jideo test | OK : T9 remplace main.py en entier, garde la signature create_app(settings) utilisée par test_health (T1) |
| T2 → T8, T9, T10, T13 | Database/Storage/errors | OK : noms identiques (insert_media, get_face, claim_next_job, cancel_queued_job, update_job champs) ; T13 ajoute jobs_created_before/media_created_before/media_in_use |
| T3 → T4, T6 | missing_models, fichiers de modèles | OK ; T4 slow dépend du téléchargement réseau de T3 Step 5 |
| T4 → T5, T6 | DetectedFace, FaceDetector, FaceSwapper, fixtures | OK |
| T5 → T6, T7, T8 | add_visible_watermark, save_image, AI_NOTICE | OK |
| T6 → T8, T9, T10 | Engine/EngineHolder, FrameResult, tests/fakes.py | OK : FakePipeline.process signature = FaceSwapPipeline.process |
| T7 → T8, T9 | probe/extract_frame/make_thumbnail/process_video, fixtures make_video/sample_video | OK : on_progress(done,total,fps) = JobContext.report_progress |
| T8 → T9, T10 | Worker, EventBus, build_handlers, job_to_public | OK |
| T9 → T10, T13 | main.py, make_client, clamp_time | OK : T10/T13 font des remplacements de chaînes exactes présentes dans le main.py de T9 |
| T9 ↔ T13 | test_health_reports_models | T13 modifie l'assertion (clé authenticated) — explicitement prévu |
| T11 → T12, T13, T14 | api.ts, Workshop.vue, App.vue, data-testid | OK : T12/T13 remplacent les fichiers en entier ; testids source-input/target-input/…-face-N/launch/job/before-after/pick-frame/preview présents |
| T1 ↔ T11 | Dockerfile, .dockerignore | OK : package-lock créé en T11 Step 4 avant le build Docker ; .dockerignore exclut frontend/e2e, sans effet sur `vite build` |
| T1 | auto-cohérence | OK |
| T2 | auto-cohérence | OK (18 tests annoncés = 6 + 7 + 5) |
| T3 | auto-cohérence | Test de checksum figé échoue volontairement jusqu'au Step 5 — prévu |
| T4–T6 | auto-cohérence | OK |
| T7 | auto-cohérence | Rotation : dépend de la version d'ffmpeg de l'image (bookworm 5.1) ; repli décrit dans le plan |
| T8–T14 | auto-cohérence | OK ; T10 test_delete_job utilise `__import__("pathlib")` (style, mineur) |

Ruling: aucun conflit bloquant ; la dépendance réseau de T3 (URLs des modèles) est assumée — si une URL est morte, l'implémenteur s'arrête (plan) et je déciderai — coût si faux : retard d'une tâche.

## Progress
Task 1: implémenté be918d9 (base 2476387)
Ruling: ajouter à backend/pyproject.toml la désactivation du cache pytest (`-p no:cacheprovider`) et un filtre ciblé du DeprecationWarning tiers starlette/anyio — la sortie de test doit être propre et le plan ne l'avait pas prévu — coût si faux : un warning tiers masqué.
Task 1: minor (deferred): jideo url() fait `source .env` (mot de passe avec caractères spéciaux) ; seul 0.0.0.0 → localhost
Task 1: minor (deferred): pas de test pour JIDEO_BIND=localhost/::1 ni secret vide généré
Task 1: fix round 1/5 (1 addressed, 0 open; commits be918d9..4b1e0ac)
Task 1: minor (deferred): backend/pyproject.toml est copié dans l'image, pas monté — toute modification exige ./jideo build
Task 1: complete (commits 2476387..4b1e0ac, review clean)
Ruling: le trailer Co-Authored-By de chaque commit suit l'attribution fournie à l'environnement du sous-agent (modèle réel), pas une valeur figée — attribution exacte — coût si faux : aucun
Task 2: minor (deferred): Storage ne valide pas job_id/media_id (clear_job_tmp("") viderait tmp/) ; delete() accepte tout fichier sous data/ (y compris sqlite/modèles)
Task 2: minor (deferred): update_job sans champ → OperationalError opaque ; has_audio relu en 0/1 ; tests storage peu stricts (atomicité, clear_tmp fichier)
Task 2: complete (commits 4b1e0ac..d48aeff, review clean)
Ruling: URL GFPGAN morte (404 sur le tag `models`) → remplacée par la même ressource du même éditeur officiel, tag `models-3.0.0` : https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gfpgan_1.4.onnx (340 299 087 octets, taille identique au miroir HF officiel facefusion) — ce n'est pas un miroir tiers, donc pas d'arrêt pour accord utilisateur ; empreinte figée au téléchargement — coût si faux : modèle incompatible détecté en Task 5 (test slow enhancer)
Task 3: implémenté eff0546 (base d48aeff)
Ruling: corriger les 2 constats plan-mandated de Task 3 — urlopen avec timeout=60 s (une coupure lève une erreur au lieu de bloquer) et main() qui intercepte ModelChecksumError/URLError/OSError/BadZipFile pour afficher un message français et renvoyer 1 — contrainte « messages en français » + install fiable — coût si faux : ~20 lignes de plus
Task 3: minor (deferred): sha256 vide = vérification sautée (fail-open) ; check ne vérifie que la présence ; pas de progression pendant les gros téléchargements ; main() peu testé
Task 3: fix round 1/5 (2 addressed, 0 open; commits eff0546..5805d76)
Task 3: minor (deferred): http.client.IncompleteRead non intercepté dans main() (coupure en plein flux → traceback)
Task 3: complete (commits d48aeff..5805d76, review clean)
Task 4: implémenté 4375338 (base 5805d76)
Ruling: FaceDetector.detect gagne un repli — si aucun visage, nouvelle détection sur l'image bordée de noir (25 % de la plus grande dimension par côté), bbox/kps ramenés dans le repère d'origine ; la fixture source_img redevient l'image brute du brief + test dédié — la spec veut accepter une « photo du visage à poser » et l'E2E (Task 14) utilise ce recadrage serré — coût si faux : une 2e détection (~0,2 s) sur les images vraiment sans visage
Task 4: minor (deferred): swapper dépend des internes d'INSwapper.get (.kps/.normed_embedding) ; detect ne valide pas l'entrée
Task 4: fix round 1/5 (2 addressed, 0 open; commits 4375338..4be5513)
Task 4: minor (deferred): filterwarnings ciblé ajouté pour le FutureWarning d'insightface (face_align estimate) dans pyproject.toml
Task 4: complete (commits 5805d76..4be5513, review clean)
Task 5: minor (deferred): _paste_back et filigrane travaillent sur toute l'image (coût mémoire/CPU sur 4096 px, surtout en vidéo) ; estimateAffinePartial2D None non géré ; test enhancer ne garde pas l'ordre des canaux (vérifié visuellement par le contrôleur)
Task 5: complete (commits 4be5513..c6305ec, review clean)
Task 6: minor (deferred): CLI sans contrôle imread None / modèles absents ; noms de fichiers modèles dupliqués entre engine/__init__ et models.py ; pipeline ne copie pas l'entrée
Task 6: complete (commits c6305ec..f6408c1, review clean)
Task 7: implémenté ce540ad (base f6408c1) ; ffmpeg 7.1 dans l'image (python:3.12-slim = Debian 13) ; repli -display_rotation appliqué au test de rotation
Ruling: Task 7 fix — (1) échec ou arrêt prématuré du décodeur = VideoError (code retour ≠ 0, ou moins de 90 % des images attendues), détail ffmpeg journalisé ; (2) messages VideoError uniquement en français, sans stderr ffmpeg ni chemin (détail → logging « jideo.video ») ; (3) test réel du repli AAC avec une source dont la copie audio échoue ; + -nostdin et Popen encodeur dans le try — contrainte « messages en français » + pas de vidéo tronquée rendue comme succès — coût si faux : une source VFR très irrégulière pourrait être rejetée à tort par le seuil de 90 %
Task 7: minor (deferred): pipes non fermés explicitement ; -shortest peut couper si l'audio source est plus court ; probe fragile (attached_pic, N/A, SAR) ; pas de timeout ffmpeg ; sortie frame_fn non validée ; test d'annulation faible
Task 7: fix round 1/5 (4 addressed, 0 open; commits ce540ad..9f45344)
Ruling: test de troncature sur MKV / MP4 faststart coupés à 50 % au lieu de MPEG-TS (ffprobe recalcule la durée d'un TS tronqué, le cas n'existe pas) — c'est le cas « l'en-tête annonce plus que le contenu », plus pertinent — coût si faux : aucun
Task 7: minor (deferred): seuil 90 % basé sur format.duration — un conteneur dont l'audio dépasse la vidéo de >10 % serait rejeté à tort
Task 7: complete (commits f6408c1..9f45344, review clean)
Task 8: implémenté fa079e8 (base 9f45344)
Ruling: Task 8 fix — (1) cancel() s'appuie sur la tâche courante mémorisée sous verrou (_current) et non sur le statut en base ; si l'annulation a été demandée pendant l'exécution, une fin normale du handler devient « cancelled » et le résultat est supprimé ; (2) started/tmp dans le try, et repli failed si la mise à jour finale échoue ; (3) stop() ne remet _thread à None que si le thread est mort ; (4) « Erreur interne » générique en français, détail dans les logs — l'API ne doit jamais annoncer une annulation qui n'a pas lieu ni laisser une tâche figée en running — coût si faux : une tâche annulée à la toute fin perd un résultat déjà calculé (comportement voulu)
Task 8: minor (deferred): QueueFull abandonne aussi les événements terminaux (resynchro côté UI via refresh sur onerror seulement)
Task 8: fix round 1/5 (5 addressed, 0 open; commits fa079e8..1e974fc)
Task 8: minor (deferred): fenêtre entre claim_next_job et _current (cancel perdu au tout début) ; start() après stop() expiré = no-op ; fichier résultat orphelin si l'écriture finale échoue
Task 8: complete (commits 9f45344..1e974fc, review clean)
Ruling: clamp_time garde une marge de max(0,05 s ; 1,5 image) avant la fin au lieu de 0,05 s fixe — à 10 i/s la dernière image est à 1,9 s et ffmpeg -ss 1,95 ne renvoie rien — coût si faux : on ne peut pas choisir la toute dernière image
Task 9: minor (deferred): nettoyage d'upload seulement sur UserError ; FileResponse sur fichier disparu → 500 ; imencode ok ignoré ; /faces accumule des lignes ; erreurs de validation FastAPI en anglais (format liste) ; Starlette met en tampon tout le corps avant la limite de taille
Task 9: complete (commits 1e974fc..6eb5b0b, review clean)
Ruling: les fichiers de test manuels vont dans data/samples/ et non data/tmp/ (data/tmp est vidé à chaque démarrage par clear_tmp) — à transmettre aux Tasks 12 et 14 — coût si faux : aucun
Task 10: minor (deferred): photo de groupe 6 visages + GFPGAN = ~28 s sur ce CPU (spec annonce 1–3 s) — piste : _paste_back sur la zone du visage seulement
Task 10: minor (deferred): retry non revalidé (modèles/médias/limite) ; delete non atomique vs claim ; params non résolus stockés (trim/t sur photo) ; message de limite arrondi « (1 s) dépasse 1 s » ; pas de test d'annulation d'une tâche en cours via l'API
Task 10: complete (commits 6eb5b0b..37138bc, review clean)
Task 11: implémenté 59e310f (base 37138bc) ; smoke Playwright headless OK (pas de navigateur interactif)
Ruling: `./jideo restart` doit recréer le conteneur (`docker compose up -d --force-recreate`) — sinon une image reconstruite n'est pas servie ; à faire dans la Task 13 (touche déjà main/infra) ou le correctif final — coût si faux : redémarrage un peu plus long
Ruling: les 3 constats Important de la Task 11 (plan-mandated) sont reportés dans les tâches qui réécrivent ces fichiers au lieu d'un tour de correction — (1) course d'upload : DropZone ignore le drop quand busy + Workshop ignore les réponses périmées (jeton par côté) → Task 12 (remplace Workshop.vue) ; (2) erreurs réseau en anglais : request() enveloppe fetch et lève ApiError(0, « Serveur injoignable. ») → Task 12 ; (3) démarrage fragile d'App.vue → déjà couvert par l'App.vue de la Task 13 (try/catch + message), à vérifier à sa revue — éviter de corriger deux fois un fichier remplacé juste après — coût si faux : si la Task 12 oublie, la revue de la Task 12 le verra
Task 11: minor (deferred): BeforeAfter sans object-fit ; onerror SSE empile des refresh et ne reconnecte pas une source fermée ; allFaces ne revient pas à true
Task 11: complete (commits 37138bc..59e310f, review clean — 3 Important reportés en Task 12/13 par ruling)
Ruling: accepter le correctif hors brief de useJobs.upsert (un statut ne recule jamais : queued < running < terminal) — la réponse POST arrivait après l’événement SSE « started » et masquait la progression — coût si faux : aucun, retry crée un nouvel id
Task 12: minor (deferred): « Fin ici » à 0 s ou durée nulle → end=0 → 422 générique ; format 0:60.0 ; String(e) pour les erreurs non-API ; une vidéo déposée côté source contourne accept
Task 12: complete (commits 59e310f..78ebaa3, review clean)
Task 13: implémenté e1651d2 (base 78ebaa3) ; .env restauré (127.0.0.1, pas de mot de passe) vérifié par le contrôleur
Ruling: Task 13 fix — (1) useJobs.connect() recrée l'EventSource s'il est fermé (et le gestionnaire 401 le ferme) ; (2) jeton de session lié au mot de passe (sel dérivé de sha256(mot de passe)) : changer le mot de passe invalide les sessions ; (3) login async avec await asyncio.sleep (ne bloque plus le pool de threads) ; (4) media_in_use protège aussi le média du visage source ; + LoginView sans String(e), logout robuste, /docs /redoc /openapi.json désactivés — sécurité en mode réseau + historique en direct exigé par le brief — coût si faux : aucun fonctionnel
Task 13: minor (deferred): pas de vérification d'Origin ; flux SSE ouvert continue après expiration ; tests manquants (cookie autre secret / expiré, PurgeThread)
Task 13: fix round 1/5 (7 addressed, 0 open; commits e1651d2..8639a43)
Task 13: minor (deferred): logout ne révoque pas le jeton côté serveur (cookie volé valable 30 j sauf changement de mot de passe)
Task 13: complete (commits 78ebaa3..8639a43, review clean)
Task 14: implémenté a926d27 (base 8639a43) ; timeout 30 s ajouté à la 1re assertion E2E (chargement paresseux des modèles à froid)
Task 14: minor (deferred): 2e test E2E non tolérant au démarrage à froid ; e2e sans ensure_env ; JIDEO_SECRET absent du tableau README ; chiffre vidéo 0,25 img/s mesuré sur durée totale de tâche
Task 14: complete (commits 8639a43..a926d27, review clean)
Final review: With fixes — 0 Critical, 4 Important (appel pypi.org par albumentations ; timeline inutilisable pour HEVC sous Linux ; anti-bruteforce contourné en parallèle ; chiffres de perf non représentatifs)
Ruling: vitesse vidéo ≈ 0,67 img/s (1 visage, sans amélioration) sur ce CPU portable 15 W est un fait matériel, pas un défaut — l'inférence des modèles domine ; spec §4.6 et README corrigés avec les mesures — coût si faux : aucun, optimisations restantes listées
Ruling: vague de correction finale unique = 4 Important + JIDEO_SECRET au README + gains peu coûteux (pas de repli padding en vidéo/aperçu, progression aussi toutes les ~2 s, url() sans `source .env`, nettoyage d'upload sur toute exception) — le reste des minors attend
Final fix wave: INTERROMPUE à la demande de l'utilisateur (déplacement hors ligne) — modifications non commitées dans l'arbre de travail (17 fichiers + test_offline.py), aucun commit après a926d27 ; à la reprise : nouvel implémenteur avec final-fix-brief.md + final-fix-report.md (s'il existe), qui vérifie ce qui est déjà fait, termine, teste et commite
Contrôleur : la section « Progression » du plan est cochée au fil de l'eau (demande utilisateur) ; commit du plan à la fin pour ne pas interférer avec les commits de l'agent
Final fix wave: terminée (commits a926d27..5f650a9) — 121 tests, typecheck/build, e2e 2/2 (1 échec au 1er passage, photo, probable délai à froid)
Final fix re-review: 9/9 ADDRESSED, aucune régression produit
Final: parked — délais E2E trop courts au démarrage à froid (Terminé 60 s pour ~57 s mesurés ; détections à 5 s) — Ruling: pas de seconde vague de correction (règle du processus) ; défaut de test, pas du produit ; correctif concret proposé à l'utilisateur (expect 30 s, Terminé 150 s/90 s, préchauffage beforeAll) — coût si faux : un échec intermittent de ./jideo e2e juste après un rebuild
Final: parked — un visage cible trouvé seulement grâce au repli avec bordure (via /faces) peut ne pas être retrouvé dans une tâche vidéo/aperçu — Ruling: conséquence assumée du correctif 6 (vitesse vidéo) ; cas rare (visage collé au bord de l'image) — coût si faux : 0 visage remplacé sur ce cas, signalé par le message de ratio
