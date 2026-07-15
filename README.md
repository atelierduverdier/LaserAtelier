# Atelier Laser

Workbench [FreeCAD](https://www.freecad.org/) pour la génération de G-code de marquage/découpe laser, avec suivi de surfaces 3D courbes, découpe multi-passes, grille de test puissance/vitesse et jobs combinant plusieurs opérations en une seule passe.

## Fonctionnalités

- **Hachures 2D** : remplissage (parallèles / croisées / défocus) sur une face 2D
- **Projection sur surface 3D** : projette un motif 2D sur une surface courbe par raycast vertical
- **Calibration kerf** : génère un carré test pour mesurer le kerf réel du laser
- **Grille de test puissance/vitesse** : job unique en grille de cellules à puissance/vitesse variables, avec étiquettes de repérage, optimisation du trajet par proximité et remplissage défocus
- **Marquage sur surface courbe** : suit le relief d'un modèle 3D (sonde exacte par raycast, ou interpolation), avec préréglages matériau et aperçu du trajet directement dans la vue 3D
- **Découpe multi-passes sur surface courbée** : combine le suivi de relief du marquage courbe avec la logique multi-passes/kerf/imbrication de la découpe à plat
- **Découpe multi-passes (matériau plat)** : passes progressives, compensation de kerf, ordre trous-avant-contour, rampe de puissance, dernière passe ralentie
- **Job combiné** : empile plusieurs opérations (marquage, découpe, grille de test) dans un seul fichier G-code avec un seul armement du laser, transition de sécurité anti-collision entre opérations
- Estimation de durée en direct, aperçu de trajet dans la vue 3D, aperçu de cadrage en fichier séparé pour vérifier le positionnement avant de lancer le job réel

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
