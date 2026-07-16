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

## Prérequis

- FreeCAD (testé sur la série 1.1)
- Le laser doit accepter du G-code au format généré (voir `laser_core.py` : `G21`/`G90`/`G94`, armement par `M3`/désarmement par `M5`, arrêt de job propre au `M2`)

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
