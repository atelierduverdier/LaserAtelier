# Atelier Laser

Workbench [FreeCAD](https://www.freecad.org/) pour la génération de G-code de marquage/découpe laser, avec suivi de surfaces 3D courbes, découpe multi-passes, grille de test puissance/vitesse et jobs combinant plusieurs opérations en une seule passe.

## Fonctionnalités

- **Hachures 2D** : remplissage (parallèles / croisées / défocus) sur une face 2D
- **Projection sur surface 3D** : projette un motif 2D sur une surface courbe (sonde par tessellation, quasi instantanée même sur un remplissage dense)
- **Calibration kerf** : génère un carré test pour mesurer le kerf réel du laser
- **Grille de test puissance/vitesse** : job unique en grille de cellules à puissance/vitesse variables, avec étiquettes de repérage, optimisation du trajet par proximité et remplissage défocus
- **Marquage sur surface courbe** : suit le relief d'un modèle 3D (sonde par tessellation, ou interpolation), avec préréglages matériau et aperçu du trajet directement dans la vue 3D
- **Découpe multi-passes sur surface courbée** : combine le suivi de relief du marquage courbe avec la logique multi-passes/kerf/imbrication de la découpe à plat
- **Découpe multi-passes (matériau plat)** : passes progressives, compensation de kerf, ordre trous-avant-contour, rampe de puissance, dernière passe ralentie
- **Job combiné** : empile plusieurs opérations (marquage, découpe, grille de test) dans un seul fichier G-code avec un seul armement du laser, transition de sécurité anti-collision entre opérations
- Estimation de durée en direct, aperçu de trajet dans la vue 3D, aperçu de cadrage en fichier séparé pour vérifier le positionnement avant de lancer le job réel

## Démo vidéo

[Vidéo de démonstration sur YouTube](https://youtu.be/KP4F4Cd287A)

## Captures d'écran

| | |
|---|---|
| ![Résultat coloré](docs/screenshots/resultat-colore.png) | ![Job combiné](docs/screenshots/job-combine.png) |
| ![Réglages de marquage](docs/screenshots/parametres-marquage.png) | ![Grille de test puissance/vitesse](docs/screenshots/grille-test-puissance-vitesse.png) |

## Performances

La sonde de hauteur Z (suivi de relief pour le marquage/découpe sur surface courbe et la projection de motifs) utilisait à l'origine une intersection géométrique OpenCascade **par point sondé** (~5 ms chacune) : sur un remplissage dense, cela représentait des dizaines de milliers d'intersections et plusieurs minutes de calcul. Elle repose maintenant sur une **tessellation unique** de la surface suivie d'une interpolation barycentrique par point (quelques microsecondes).

Concrètement :

- **Tessellation unique** : la surface 3D est convertie une seule fois, au début du calcul, en un maillage de petits triangles (comme les facettes d'un modèle pour l'impression 3D). C'est OpenCascade qui s'en charge, en C++, en quelques millisecondes. Les triangles sont ensuite rangés dans une grille XY pour retrouver instantanément ceux qui se trouvent sous un point donné.
- **Interpolation barycentrique par point** : pour connaître la hauteur Z de la surface sous une position (X, Y), il suffit alors de trouver le triangle qui contient ce point (vu de dessus) et de calculer le Z par une moyenne pondérée des hauteurs de ses trois sommets (les "coordonnées barycentriques" : le poids de chaque sommet dépend de la proximité du point à celui-ci). C'est une poignée de multiplications et d'additions — d'où les quelques microsecondes, là où l'ancienne méthode reconstruisait une intersection géométrique complète ligne/solide à chaque point.

L'astuce est donc de payer une fois un petit coût de préparation (le maillage) pour rendre ensuite chaque requête quasi gratuite, au lieu de payer le prix fort à chacune des dizaines de milliers de requêtes.

Mesures sur une plaque ondulée 100×60 mm, hachures espacées de 0,5 mm (~48 000 points de trajectoire) :

| Calcul | Avant | Après | Gain |
|---|---:|---:|---:|
| Projection du motif sur la surface 3D | 66,2 s | 0,06 s | ×1200 |
| G-code marquage courbe (1er calcul) | 107,0 s | 0,18 s | ×600 |
| G-code marquage courbe (recalcul) | 11,8 s | 0,18 s | ×65 |

Les hachures 2D bénéficient de la même approche (clipping paramétrique de chaque ligne sur la tessellation des faces, au lieu d'une opération booléenne par ligne et par face) :

| Calcul | Avant | Après | Gain |
|---|---:|---:|---:|
| Hachures 0,2 mm sur 24 faces à trou | 2,6 s | 0,08 s | ×33 |
| Grille de test 6×6, hachures 0,2 mm | 1,1 s | 0,06 s | ×17 |

La précision est préservée : l'écart Z entre le maillage et la vraie surface est borné à 0,05 mm (constante `MESH_PROBE_DEVIATION_MM`), validé contre l'ancien raycast exact sur 300 points aléatoires (erreur max mesurée : 0,046 mm) — négligeable face à la tolérance de focus du laser (~0,1 mm).

## Matériel testé

Cet atelier a été développé et testé avec le module laser **LT-80W-AA-PRO** (diode 10 W optiques). Les préréglages de hauteur de bec par épaisseur (`FOCUS_TABLE` dans `laser_core.py`) proviennent du tableau constructeur de ce module.

**Modification matérielle importante** : la pièce carrée qui entoure le nez du laser a été **retirée**, afin de pouvoir suivre les surfaces courbes sans collision. Le contrôle de dégagement anti-collision intégré à l'atelier (modes marquage/découpe sur surface courbe) modélise donc uniquement le nez conique restant, avec les dimensions suivantes (constantes `NOZZLE_*` dans `laser_core.py`) :

| Dimension | Valeur |
|---|---|
| Diamètre à la pointe du nez (point le plus bas) | 5 mm |
| Diamètre au sommet du cône | 16 mm |
| Hauteur du cône (cylindre de même diamètre au-dessus) | 18 mm |

### Adapter à un autre laser

Si ton laser a un nez de géométrie différente, **le contrôle anti-collision doit être adapté avant d'utiliser les modes sur surface courbe** — sinon il sous-estimera (ou surestimera) les collisions. Pas besoin de toucher au code : ajoute une clé `nozzle` dans le fichier de configuration `laser_atelier_config.json` (dossier de configuration utilisateur de FreeCAD) :

```json
{"nozzle": {"bottom_diameter_mm": 5.0, "top_diameter_mm": 16.0, "height_mm": 18.0}}
```

Cas fréquents :

- **Nez conique** (comme le LT-80W modifié) : diamètre à la pointe, diamètre au sommet du cône, hauteur du cône.
- **Tube droit jusqu'en bas** (pas de cône, section constante — fréquent sur d'autres modules) : mettre `bottom_diameter_mm` = `top_diameter_mm` = diamètre du tube. Le modèle devient alors un cylindre : toute matière plus haute que la pointe sous l'empreinte du tube déclenche le relevage, ce qui est le comportement attendu.
- **Tube de section rectangulaire** : entrer la **diagonale** de la section comme diamètre. Le modèle étant de révolution, la diagonale couvre le pire cas quelle que soit l'orientation du tube par rapport au déplacement.

Une configuration incohérente (diamètre bas > haut, valeurs négatives) est ignorée avec un avertissement dans la vue Rapport, et les valeurs par défaut sont conservées.

À noter également : le tableau `FOCUS_TABLE` (hauteur de bec par épaisseur pour la découpe à plat) provient du constructeur du LT-80W — à ajuster dans `laser_core.py` pour un autre module.

## Prérequis

- FreeCAD (testé sur la série 1.1)
- Le laser doit accepter du G-code au format généré (voir `laser_core.py`) :
  en-tête `G21`/`G90`/`G94`/`G43 H100`, armement unique par `M3 $1`
  (faisceau à zéro), puissance par segment `S… $1`, `S0 $1` sur les
  rapides, désarmement `M5 $1`, arrêt de job propre au `M2`
- **Prérequis machine avant de lancer un fichier généré** : avoir fait
  `T100 M6` dans la session LinuxCNC. Le `G43 H100` de l'en-tête
  applique les offsets X/Y et le Z palpé de l'outil laser (T100) à ce
  moment-là ; sans lui, les coordonnées seraient interprétées en
  position broche et non nez laser (focus faux, X/Y décalés). Le
  prérequis est rappelé en commentaire dans chaque fichier généré.
- Le sélecteur multi-broche `$1` et la compensation d'outil sont pensés
  pour LinuxCNC (laser = spindle 1, outil T100). Pour un contrôleur qui
  ne les supporte pas (GRBL...), adapter `SPINDLE_SELECT` et
  `CMD_TOOL_COMP` dans `laser_core.py`

## Installation

Clone ce dépôt directement dans le dossier `Mod` de FreeCAD :

```bash
git clone https://github.com/atelierduverdier/LaserAtelier.git ~/.local/share/FreeCAD/<version>/Mod/LaserAtelier
```

(adapte `<version>` à ta version de FreeCAD, par ex. `v1-1`). Redémarre FreeCAD, l'atelier "Atelier Laser" apparaît dans le sélecteur d'ateliers.

## Utilisation

Sélectionne la géométrie appropriée (voir l'info-bulle de chaque bouton) puis lance la commande correspondante depuis la barre d'outils ou le menu "Atelier Laser". Chaque panneau de tâches propose ses propres réglages (puissance, vitesse, épaisseur...), un aperçu de durée en direct, et un bouton pour générer un aperçu de cadrage (fichier séparé, laser éteint) à vérifier avant de lancer le job réel.

## Configuration

Les champs de G-code personnalisé (avant/après job) et les préréglages matériau sont mémorisés entre deux lancements de FreeCAD dans un fichier de configuration JSON (`laser_atelier_config.json`, dans le dossier de configuration utilisateur de FreeCAD).
