# Les panneaux de l'atelier

> 📖 Pour la **documentation complète en images** (présentation, installation, flux de travail, calibration, FAQ…), voir [`index.html`](index.html) — la page web de l'atelier, prête pour GitHub Pages. Cette galerie-ci ne rassemble que les captures brutes de chaque panneau.

Captures d'écran de chaque mode (panneau complet, largeur réelle du panneau des tâches). Générées automatiquement depuis FreeCAD — pour les régénérer après une évolution de l'interface : instancier chaque `TaskPanel*` et capturer `panel.form.widget()` (le contenu entier du `QScrollArea`, sans avoir à faire défiler).

## Découverte

### Guide rapide
Le point d'entrée : flux de travail en 6 étapes, « quel mode pour quoi ? », règles de la maison.

![Guide rapide](screenshots/panneaux/01_guide.png)

## Gravure à plat

### Hachures 2D (géométrie)
Remplit une face de hachures (parallèles / croisées / défocus) — géométrie seule, à graver ensuite avec le Marquage.

![Hachures 2D](screenshots/panneaux/02_hachures_2d.png)

### Gravure remplie (noir)
Texte/forme en noir plein : remplissage défocus rentré du bord + contour net, styles de trait, compensation puissance/défocus.

![Gravure remplie](screenshots/panneaux/03_gravure_remplie.png)

### Gravure photo (trame de points)
Image → trame de points laser (diffusion Floyd-Steinberg ou durée variable), aperçu du tramage en direct.

![Gravure photo](screenshots/panneaux/04_gravure_photo.png)

## Sur surface 3D

### Projection sur surface 3D
Motifs 2D projetés sur une surface courbe — on sélectionne pendant que le panneau est ouvert, état affiché en direct.

![Projection](screenshots/panneaux/05_projection.png)

### Marquage de motif (plat ou courbe)
Grave un motif filaire, à plat ou en suivant le relief, avec les 5 styles de trait et le nuancier.

![Marquage](screenshots/panneaux/06_marquage.png)

### Découpe multi-passes (courbe)
Découpe en plusieurs passes en suivant le relief d'une surface courbe.

![Découpe courbe](screenshots/panneaux/07_decoupe_courbe.png)

## Découpe

### Découpe multi-passes (matériau plat)
Passes progressives, kerf, trous d'abord, attaches, amorce, copies en matrice.

![Découpe plate](screenshots/panneaux/08_decoupe_plate.png)

## Tests & calibration

### Calibration kerf
Carré test pour mesurer le kerf réel.

![Calibration kerf](screenshots/panneaux/09_calibration_kerf.png)

### Grille de test puissance/vitesse
Matrice de cellules S×F étiquetée, hauteur (Z) de test réglable.

![Grille de test](screenshots/panneaux/10_grille_test.png)

### Test rampe puissance/vitesse (lignes)
Lignes continues, une par vitesse, puissance croissante (et rampe Z optionnelle), règle graduée.

![Rampe puissance/vitesse](screenshots/panneaux/11_rampe_puissance.png)

### Bande de calibration défocus
Traits à hauteurs croissantes pour mesurer le foyer et la divergence — alimente la calibration des Préférences.

![Calibration défocus](screenshots/panneaux/12_calibration_defocus.png)

### Test des offsets X/Y du laser
Job mixte fraise + laser : l'écart entre les deux croix corrige `tool.tbl`.

![Test des offsets](screenshots/panneaux/13_test_offsets.png)

### Nuancier matériau
La palette de gris mesurée d'un matériau (tons noirceur/S/F/défocus/largeur), appliquée d'un clic dans les modes.

![Nuancier](screenshots/panneaux/14_nuancier.png)

## Assemblage & réglages

### Job combiné
Plusieurs opérations dans un seul fichier G-code, un seul armement.

![Job combiné](screenshots/panneaux/15_job_combine.png)

### Préférences
Tous les réglages machine centralisés : calibration du point, Z de travail, fluence, bec, sécurité…

![Préférences](screenshots/panneaux/16_preferences.png)
