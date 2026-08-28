# Les panneaux de l'atelier

> 📖 Pour la **documentation complète en images** (présentation, installation, flux de travail, calibration, FAQ…), voir [`index.html`](index.html) — la page web de l'atelier, prête pour GitHub Pages. Cette galerie-ci ne rassemble que les captures brutes de chaque panneau.

Captures d'écran de chaque mode (panneau complet, largeur réelle du panneau des tâches).

Pour les régénérer après une évolution de l'interface, **sans toucher à la session FreeCAD
ouverte** — une seule commande, qui refait la galerie ci-dessous ET les images du manuel :

```bash
python3 tests/lancer.py --captures
```

```bash
python3 tests/lancer.py --captures halftone
```

La seconde forme n'en refait qu'un. Le lanceur passe par le même harnais que les tests, donc
la config est redirigée vers une **copie jetable** : capturer ne peut pas écrire dans les
mesures prises au pied à coulisse. Il impose aussi les fontes du système — sans elles Qt
retombe sur une chasse fixe et les ①②③ des sections sortent en « 0 », une capture
lisible mais qui ne ressemble plus aux autres. Chaque panneau est instancié hors écran et
recadré en bas. Largeurs de la maison : **453** px ici, **430** px pour `docs/manuel_img/`
(le manuel).

> L'ancienne recette — `outils/capturer_panneau.py` lancé à la main avec le python d'une
> AppImage montée — pilotait la vraie config et citait un chemin `/tmp/.mount_FreeCA…` qui
> change à chaque lancement de FreeCAD. Elle ne vaut plus depuis que ce poste tourne le
> **paquet système** (16/08/2026).

## Découverte

### Guide rapide
Le point d'entrée : flux de travail en 6 étapes, « quel mode pour quoi ? », règles de la maison.

![Guide rapide](screenshots/panneaux/01_guide.png)

## Import de dessins

### Importer un dessin SVG
Lit le `.svg` directement et crée **un objet par tracé d'origine**, sélectionnable individuellement — sans le détour par le DXF, qui émiettait un crâne de 23 tracés en plus de 210 fragments. La couleur de remplissage est reprise sur l'objet, pour les distinguer à l'œil.

![Importer un dessin SVG](screenshots/panneaux/20_import_svg.png)

## Gravure à plat

### Hachures 2D (géométrie)
Remplit une face de hachures (parallèles / croisées / défocus) — géométrie seule, à graver ensuite avec le Marquage.

![Hachures 2D](screenshots/panneaux/02_hachures_2d.png)

### Texte (trait simple)
Du texte en police **mono-trait** : une seule passe de plume par branche, pas un contour rempli. 45 polices (EMS 29, Hershey 13, Twin Sans, Relief SingleLine — OFL ou domaine public — plus **Verdier**, dessinée pour l'atelier : chapeau melon sur `¤`, œ et Œ tracés), et le bouton « Voir… » les écrit toutes avec votre texte pour choisir en les voyant. Crée un objet fil, à graver ensuite avec Marquage.

![Texte (trait simple)](screenshots/panneaux/18_text.png)

### Calligraphie (pleins et déliés)
Un texte gravé dans une **vraie police calligraphique** (`.otf`/`.ttf` lue sur votre disque) en un seul passage : on extrait le squelette de la lettre et sa largeur locale, et la largeur devient une **hauteur Z** — la tête se lève pour élargir le trait dans les pleins, redescend pour les déliés. Le verdict dit si les pleins demandés tiennent dans ce que le matériau sait donner, et propose la taille qui les ferait tenir.

![Calligraphie (pleins et déliés)](screenshots/panneaux/21_calligraphie.png)

### Texte gravé (contour)
Le pendant du précédent pour les polices **classiques**. Une calligraphie est le dessin d'une plume — son axe médian *est* le geste ; une police classique n'a pas de plume, son **contour est son dessin**, et en extraire un axe réduirait les empattements à de petites barres. Ce mode trace donc le pourtour exact du glyphe, pris sur les vraies courbes de la police, à graver ensuite avec **Marquage** (lettres creuses) ou **Gravure remplie** (lettres pleines) — les contreformes se creusent toutes seules.

![Texte gravé (contour)](screenshots/panneaux/22_texte_contour.png)

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

### Assistant matériau
Caractériser un matériau du début à la fin, dans l'ordre : graver les trois planches, saisir les mesures (au pied à coulisse ou **sur la photo redressée**, le cadrage de chaque trait étant calculé), puis en déduire largeurs, espacements et régimes. C'est d'ici que sort la table de brûlures dont dépendent le défocus, le fuseau Z et la calligraphie.

![Assistant matériau](screenshots/panneaux/17_assistant.png)

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

### Catalogue (planche d'exemples)
Une planche d'**exemples** gravée en un seul job : styles de Marquage, texte mono-trait, gravure remplie, chacun étiqueté avec ses réglages. À garder sur l'établi — c'est l'échantillonnier auquel on compare une idée avant de la graver en grand.

![Catalogue (planche d'exemples)](screenshots/panneaux/19_catalogue.png)

## Assemblage & réglages

### Job combiné
Plusieurs opérations dans un seul fichier G-code, un seul armement.

![Job combiné](screenshots/panneaux/15_job_combine.png)

### Préférences
Tous les réglages machine centralisés : calibration du point, Z de travail, fluence, bec, sécurité…

![Préférences](screenshots/panneaux/16_preferences.png)
