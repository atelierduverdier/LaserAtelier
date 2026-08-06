# Atelier Laser

<p align="center"><img src="resources/logo.svg" alt="Atelier Laser — PrintNC" width="360"></p>
<p align="center"><img src="resources/icons/chapeau.svg" alt="" width="56"><br><sub><b>v2.99.38</b> — Le petit chapeau en coin de chaque icône est la signature de l'<a href="https://atelierduverdier.fr">Atelier du Verdier</a>.<br>© Atelier du Verdier — licence <a href="LICENSE">LGPL-2.1-or-later</a>.</sub></p>
<p align="center"><a href="https://ko-fi.com/atelierduverdier"><b>☕ L'atelier vous est utile ? Soutenez-le sur Ko-fi</b></a></p>

> **≈ 211 heures pour en arriver là**, du 15/07/2026 au 06/08/2026 : ≈ 182 h de développement (553 commits, 262 versions) et ≈ 29 h d'atelier, dont **11,4 h de laser** chronométrées sur les 70 fichiers gravés — 495 m de trait brûlé et 283 mesures relevées sur le bois.
>
> Le code est écrit par Claude (Anthropic). Christophe Le Verdier décide, éprouve chaque version sur le bois et tranche : la plupart des défauts corrigés ici ont été trouvés en regardant une planche, pas en relisant du code.
>
> <sub>Chiffres recalculés par `python3 outils/chiffrer_effort.py` — jamais recopiés à la main.</sub>

Workbench [FreeCAD](https://www.freecad.org/) pour la génération de G-code de marquage/découpe laser : gravure noir plein de textes/formes, suivi de surfaces 3D courbes, découpe multi-passes, grilles de test et de calibration, et jobs combinant plusieurs opérations en une seule passe.

> 📖 **Documentation complète** : une page web autonome présente tout l'atelier (présentation, installation, flux de travail, les 20 modes en images, calibration, préférences, G-code, FAQ) dans [`docs/index.html`](docs/index.html). Elle est prête pour **GitHub Pages** : dans les réglages du dépôt, activer *Pages* → source *Deploy from a branch* → branche `main`, dossier `/docs` ; la doc est alors publiée à l'adresse `https://atelierduverdier.github.io/LaserAtelier/`. Le fichier fonctionne aussi tel quel si on l'ouvre en local ou qu'on copie le dossier `docs/` sur un autre site.

## Fonctionnalités

> Ce README décrit l'atelier **tel qu'il fonctionne**. L'historique — ce qui n'allait pas, ce que le bois a dit, ce qui a été essayé et écarté — vit dans le manuel, chapitre 14 «&nbsp;[Journal de l'atelier](docs/Manuel-LaserAtelier.pdf)&nbsp;», 87 entrées avec leurs mesures.

Les modes sont regroupés par thème dans **neuf barres d'outils nommées** (Découverte, Calibrer le laser, Ajouter un matériau, Dessins, Gravure à plat, Sur surface 3D, Découpe, Assemblage, Référence et réglages) et dans un menu unique. Une barre nommée se déplace, se masque et se replie séparément — les séparateurs d'une barre unique ne se voyaient pas ; chacune reçoit en plus un fond légèrement teinté, en renfort du nom et jamais à sa place. Le **Guide rapide** (première icône, livre ouvert) résume le flux de travail (calibrer → tester → motif → G-code → cadrage → graver) et « quel mode pour quoi ? » — le point d'entrée pour découvrir l'atelier. **Workflow type** : créer/charger le tracé (SVG, ShapeString, sketch) → le placer en X/Y par rapport au futur zéro pièce → le **projeter** sur la pièce (contrôle visuel : le tracé est posé sur la surface, plate ou 3D) → graver avec **Marquage** (traits, sélectionner le projeté) ou **Gravure remplie** (noir plein, sélectionner la forme fermée *source*). La hauteur Z du document est visuelle : le G-code suppose toujours zéro Z machine sur la surface gravée, et un job = une seule surface de référence. Chaque panneau ouvre sur un résumé court avec un bouton « En savoir plus » (détails repliés) et, pour les concepts clés, un petit schéma explicatif (cône de défocus, axes de la grille, rampe, projection…).

**Import de dessins**
- **Importer un dessin SVG** : lit le `.svg` directement et crée **un objet par tracé d'origine**, sélectionnable séparément — sans le détour par le DXF, qui émiettait un crâne de 23 tracés en **plus de 210 fragments** (plus les `_BlockDefinitions`/`Layer` de la plomberie DXF). La couleur de remplissage de chaque tracé est reportée sur l'objet (`LineColor`) pour les distinguer à l'œil sans rouvrir Inkscape. Parseur autonome (`svg_import.py`), courbes aplaties en segments comme partout ailleurs dans l'atelier. **Hors périmètre, annoncé par un avertissement plutôt que subi en silence** : `<use>`, dégradés, `<clipPath>`/masques, `<image>` matricielles, et les classes CSS d'un bloc `<style>`.

**Gravure à plat**
- **Hachures 2D (géométrie)** : remplissage (parallèles / croisées / défocus) sur une face 2D — crée la géométrie des hachures Option **contour** : le bord de la forme (trous compris) est ajouté à l'objet créé — hachures + contour gravés en une seule opération Marquage.
- **Calligraphie (pleins et déliés)** : grave un texte dans une **vraie police calligraphique** (`.otf`/`.ttf` lue sur ton disque) en **un seul passage**. On extrait le squelette de la lettre et sa largeur locale ; la largeur devient une **hauteur Z** — la tête se lève pour élargir le trait dans les pleins, redescend pour les déliés. Rien n'est rempli ni repassé. Le panneau dit si les pleins demandés tiennent dans ce que le bois sait donner, et propose la taille qui les ferait tenir. «&nbsp;Poser le tracé dans le document&nbsp;» crée le trajet en fil dans l'arbre pour le **placer sur la pièce** ; la génération suit ce placement. *Les polices ne sont pas fournies : celles du commerce sont presque toutes en licence « usage personnel ».*

  **Deux sources de pleins et déliés** : les *extraire* d'une police calligraphique (le squelette et la largeur locale sont lus dans le dessin de la lettre), ou les *calculer* sur une police **mono-trait** avec une plume simulée — `largeur = mini + (maxi − mini) × |sin(angle du trait − angle du bec)|`. Un mono-trait *est* un squelette : rien à en extraire, mais la **direction** de chaque trait y est exacte, et c'est tout ce dont une plume à bec large a besoin. Trois réglages : l'**angle du bec** (25° par défaut), l'**épaisseur du plein** (16 % de la hauteur) et le **contraste** (16:1). Une plume est *grasse* — c'est ce qui la distingue d'un trait épaissi. Ça marche sur les 45 polices mono-trait.
- **Texte gravé (contour)** : le pendant du précédent pour les polices **classiques**. Là où une calligraphie est le dessin d'une plume — son axe médian *est* le geste —, une police classique n'a pas de plume : son **contour est son dessin**, et en extraire un axe réduit les empattements à de petites barres. Ce mode trace donc le **pourtour exact** du glyphe, pris sur les vraies courbes de la police (pas retracé sur une image), aplati à 0,02 mm. Il pose les contours dans le document, à graver ensuite avec **Marquage** (lettres creuses) ou **Gravure remplie** (lettres pleines) — les contreformes se creusent toutes seules.
- **Texte (trait simple)** : grave du texte en **police mono-trait** (Hershey Sans 1-stroke, domaine public) — chaque lettre dessinée d'un seul trait par branche, comme un traceur à plume, au lieu d'un contour rempli. Majuscules, minuscules, chiffres et accents ; hauteur et espacements réglables. Crée un objet fil à graver avec **Marquage** (idéal au gros point / défocus).

  Parmi les 45 : **Verdier — la police de l'atelier, **dessinée trait par trait** par `outils/creer_police_verdier.py` : aucune fonte tierce, donc aucune licence à respecter, et elle porte le **chapeau melon** de la maison en glyphe — un **bouton ¤** à côté du champ texte l'insère (au clavier : AltGr + $) ainsi que les **œ / Œ** que seule Relief SingleLine avait avant elle.
- **Gravure remplie (noir)** : grave un texte/forme 2D en **noir plein** — remplissage par hachures en défocus (point élargi, automatiquement **rentré du rayon de point** pour ne pas déborder du bord, avec un liseré qui ferme les blancs le long des bords) **puis** contour repassé net au foyer (épaisseur de trait réglable). Préréglages matériau. **Styles de trait** au choix pour le remplissage et le contour : trait plein, **tirets** (faisceau pulsé, mouvement continu), **pointillé** (vrais points ronds gravés en micro-traits — jamais de pulse G4 faisceau allumé, compatible puissance asservie ; gros points doux en défocus), ou **vague défocus** (le Z oscille entre le foyer et un défocus max : le trait varie continûment en largeur et en intensité, effet calligraphique ; amplitude calculée par la calibration du point, avertissement si la vitesse Z crête dépasse la limite de l'axe). **Remplissage en dégradé** : la puissance varie linéairement le long d'une direction réglable (0° = gauche→droite), de la puissance de remplissage au « S en fin de dégradé » — l'espacement des hachures est resserré sur la brûlure mesurée de la puissance la plus faible pour rester uniforme sur toute la forme.
- **Gravure photo (trame de points)** : convertit une image (PNG/JPG…) en gravure, par **huit tramages** au choix. Ils ne sont pas huit variantes du même rendu : trois demandent au bois de *produire* un gris (via la calibration), cinq le fabriquent par une **géométrie** — une densité, une surface, une épaisseur — et ne dépendent donc d'aucune courbe.

  | Tramage | Le gris vient de… | Calibration |
  |---|---|---|
  | **Diffusion (Floyd-Steinberg)** | la densité de points identiques | aucune |
  | **Durée variable** | la durée de chaque point | aucune |
  | **Lignes calibrées (nuancier)** | la puissance, modulée **pixel par pixel** le long d'un balayage continu | **nuancier mesuré** |
  | **Diffusion en lignes (points fins)** | des pixels allumés/éteints le long d'un balayage continu | aucune |
  | **Gros points Z** | le **diamètre** du point, porté par la hauteur Z | cône du point |
  | **Similigravure (trame 45°)** | la **surface** du point dans une maille régulière (aucun moiré) | aucune |
  | **Lignes gravées (trait qui enfle)** | l'**épaisseur** d'un trait jamais coupé | largeurs brûlées |
  | **Spirale** | la même épaisseur, enroulée du centre au bord, sans un seul demi-tour | largeurs brûlées |

  Les trois derniers rendent le gris par une marque visible à l'œil nu : ils réclament de la place, et le panneau le dit en dessous de 100 mm de large. Les points sont gravés en **micro-traits**, jamais en pulse `G4` à l'arrêt — compatible avec une puissance asservie à la vitesse réelle (HAL PrintNC).

  Réglages qui changent le résultat : **seuil blanc** (sous cette noirceur, bois nu — sans lui un pixel blanc gravait quand même 33 % de couverture), **sous le seuil** au choix *bois nu* (net, pour un logo) ou *pointillé dégressif* (doux, pour une photo), **puissance maxi du trait** (92 % à l'atelier : au-delà on creuse sans noircir), **défocus du trait** limité aux hauteurs réellement mesurées, **fuseau par la hauteur Z** pour la spirale (la largeur vient du Z, pas de la puissance : plus de marches), **tonalité (gamma)** avec aperçu en direct, option **négatif**. Outils&nbsp;: **mire des tramages** (le même dégradé gravé par chacun, en bandes étiquetées), **photo de démonstration** (Maupassant par Nadar, 1888, domaine public) et **préréglages ★** — portrait qualité, essai rapide, équilibré, artistique.

**Sur surface 3D**
- **Projection sur surface 3D** : projette un motif 2D sur une surface courbe (sonde par tessellation, quasi instantanée même sur un remplissage dense). Le panneau s'ouvre d'abord, puis on sélectionne les motifs 2D et la surface 3D dans la vue (état reconnu affiché en direct) avant de valider.
- **Marquage de motif (plat ou courbe)** : grave un motif filaire à plat, ou en suivant le relief d'un modèle 3D (sonde par tessellation), avec préréglages matériau et aperçu du trajet dans la vue 3D. **Huit styles de trait**, dont trois s'appellent « dégradé » sans faire la même chose :

  | Style | Ce qui varie | À savoir |
  |---|---|---|
  | **Trait plein** | rien | la référence |
  | **Tirets** | faisceau pulsé, mouvement continu | |
  | **Pointillé** | vrais points ronds, en micro-traits | jamais de pulse à l'arrêt |
  | **Vague défocus** | le Z oscille : largeur et intensité ondulent | effet calligraphique |
  | **Défocus (point élargi)** | Z constant au-dessus du foyer | noircit un remplissage en un passage |
  | **Dégradé de largeur (sur la pièce)** | la largeur suit la **position**, selon un angle | pour des hachures : la zone s'ombre d'un bord à l'autre |
  | **Dégradé de largeur (le long du tracé)** | la largeur suit le **parcours** | sur une spirale, seul lui donne un vrai fuseau extérieur→centre |
  | **Dégradé de puissance (le long du tracé)** | la **teinte** : Z constant, S rampe | le vrai dégradé clair→foncé ; gratuit avec `M67` |

  Sur une **boucle fermée**, les dégradés le long du tracé offrent au choix la *marche visible* à la fermeture ou l'*aller-retour* (valeur de fin atteinte à mi-parcours, boucle refermée sans raccord). Chaque trait sélectionné porte sa **rampe entière**, donc le résultat ne dépend pas de l'ordre de parcours. Une case **« faire varier aussi la puissance »** superpose une rampe de S aux deux dégradés de largeur — sans elle, la fluence évolue en 1/largeur et une spirale sort marbrée au bout large, carbonisée au bout fin ; le bouton **« Compenser la fluence »** calcule la puissance de fin qui garde la teinte, et **avertit quand elle tombe sous la plus basse puissance mesurée**. Borne à connaître : le point au foyer fait 0,30 mm, on ne descend pas sous cette largeur optique.

  Deux planches d'aide au choix : la **mire des styles** (le même trait droit par style, bandes étiquetées — elle en grave **6**, les deux dégradés le long du tracé n'y sont pas) et la **planche des styles**, un même mot exemple gravé dans chaque style, numéroté et légendé au foyer : le rendu réel sur de vraies lettres, à garder comme référence.
- **Découpe multi-passes sur surface courbée** : combine le suivi de relief du marquage courbe avec la logique multi-passes/kerf/imbrication de la découpe à plat.

**Découpe**
- **Découpe multi-passes (matériau plat)** : passes progressives, compensation de kerf, ordre trous-avant-contour, rampe de puissance, dernière passe ralentie. **Attaches (tabs)** : ponts de matière non coupés (nombre/longueur/hauteur réglables) qui retiennent la pièce — et la chute des trous — jusqu'à la fin du job, seules les passes profondes les sautent. **Amorce (lead-in)** : le faisceau s'allume dans la chute (extérieur d'une pièce, intérieur d'un trou) puis rejoint le contour — la verrue d'allumage reste hors du bord fini. **Copies en matrice** : réplique la sélection en n×m au pas choisi pour découper une série en un seul job. Les tracés **ouverts** sont coupés en aller-retour (sens alterné à chaque passe).

**Tests & calibration**
- **Calibration kerf** : deux géométries de test à découper ensuite. Le **carré** sert à *mesurer* le kerf (kerf = taille dessinée − taille mesurée au pied à coulisse). Le **tenon + mortaise** sert à *valider l'ajustement* une fois le kerf connu : un tenon (pièce mâle) et une rangée de mortaises au même nominal mais à jeu croissant — on découpe avec la compensation de kerf trouvée, on insère le tenon dans chaque mortaise et on retient le jeu qui donne le bon ajustement (serré pour un collage, glissant pour du démontable). Le mode crée **deux objets** : **« découpe »** (les contours seuls) et **« gravure »** (le jeu sous chaque mortaise + la cote sur le tenon de référence). Le texte est ainsi *marqué à faible puissance* — opération distincte de la découpe — au lieu d'être coupé : on grave puis on découpe (ou on enchaîne via Job combiné).
- **Assistant matériau** : l'étape qui caractérise un bois. Grave les **planches de calibration** (1 au foyer, 2 en défocus, 2b en défocus profond), puis on mesure la largeur de chaque trait — le cadrage de mesure est **automatique**, il n'y a qu'à ajuster et valider. Ces largeurs calent le remplissage, le bouton « Auto (½ point) » des Hachures et le tramage « Lignes gravées ». Les photos redressées sont rangées à l'échelle exacte, avec le nom du laser dans le fichier : une largeur brûlée ne veut rien dire pour un autre module, et veut tout dire pour le même.

- **Grille de test puissance/vitesse** : job unique en grille de cellules à puissance/vitesse variables, étiquettes de repérage, **cadre net au foyer** autour de chaque cellule, trajet optimisé par proximité, remplissage défocus et préréglages matériau. Un menu **« Je veux obtenir »** remplit toute la grille selon la donnée cherchée — quatre recettes, et ce ne sont pas quatre variantes du même essai :

  | Objectif | Ce qu'il grave | Pour quoi faire |
  |---|---|---|
  | **Des TONS — clairs, au point élargi** | 16 aplats, S200/F4000 (≈ 5 %) à S600/F1000 (≈ 74 %) | compléter le **bas** du nuancier, celui qui manque presque toujours |
  | **Des TONS — noirceur en aplat (photo)** | des aplats, **une seule vitesse**, le pas d'une vraie photo | c'est elle qui alimente la courbe noirceur → énergie, donc la photo calibrée et le « ton sur mesure » |
  | **Des LARGEURS de trait — défocus libre** | traits isolés et horizontaux, vitesses lentes | à n'employer qu'à un défocus *autre* que 15 ou 36, la Planche 2 couvrant ceux-là avec un cadrage automatique |
  | **Une DÉCOUPE** | contours seuls | trouver la case qui traverse proprement en une passe |

  **La bande de tons se cale sur le matériau** choisi en tête de ① : l'atelier lit les cases **vides** des planches 1/2/2b — une case vide veut dire qu'il n'y avait rien à mesurer — et en tire la **vitesse** (ramenée dans la plage où ce bois a été vu marquer) et le **plancher de puissance** (pour que la case la plus claire marque encore). La note dit ce qui a été changé et sur quelle mesure. Sur un matériau jamais mesuré, rien n'est recalé et c'est annoncé : cette première planche est un **repérage**, ses cases vierges sont elles aussi une mesure, à reporter avec une noirceur de 0. Les puissances sont **volontairement mélangées** sur la planche : rangées par ordre croissant, les cases se jugent les unes par rapport aux autres et l'œil fabrique une progression qui n'existe pas.

  Le report des tons se fait **sur place**, dans « Noirceur jugée à l'œil » au bas de la section ②. Le **défocus des cellules est libre** : la saisie ② ouvre une grille pour la hauteur demandée même si ce niveau n'a jamais été mesuré — mais un niveau ne compte comme ancrage d'interpolation que s'il porte **au moins deux puissances**. « Enregistrer les mesures » **fusionne** au lieu de remplacer. Champ **Hauteur (Z) de test** pour rejouer la même matrice à une autre hauteur, et **style de trait** du remplissage (plein / tirets / pointillé).
- **Catalogue (planche de référence)** : grave en **un seul job** une planche de référence — les **6 styles de trait du Marquage** (sur un mot exemple) + un exemple de **Gravure remplie**, chaque bloc titré, avec **aperçu photo** (rendu réaliste, chaque style bien distinct). À graver sur une chute une fois les réglages calés : on voit le rendu réel de chaque style sur son matériau. La gravure photo se teste dans son propre mode (Gravure photo).
- **Test rampe puissance/vitesse (lignes)** : grave de longues lignes, **une par vitesse**, chacune parcourue avec une puissance qui **monte progressivement** de gauche (min) à droite (max). On lit d'un coup, à chaque vitesse, à partir de quelle puissance le trait commence à marquer et où il sature — le complément **continu** de la grille de cellules discrètes. Option **rampe de hauteur (Z)** : la hauteur du bec monte *aussi* le long de chaque ligne, de la focale (gauche) à une hauteur de fin (droite), en même temps que la puissance — pour tester à chaque vitesse l'effet combiné puissance croissante + défocus croissant. Étiquettes vitesse (F) à gauche, et **règle de graduation de puissance** sous la première ligne : traits verticaux à des valeurs de S rondes (bornes + paliers intermédiaires), valeurs écrites en **chiffres verticaux** (empilés) pour tenir dans l'espacement serré — on lit d'un coup la puissance sous n'importe quel point du trait.
- **Bande de calibration défocus** : grave une rangée de courts traits à hauteurs de bec croissantes, étiquetés en **hauteur** (à gauche) et en **puissance** (à droite), avec **rampe de puissance** optionnelle — pour mesurer le foyer (trait le plus fin) et la divergence du point, et renseigner la calibration défocus une bonne fois. Option **plusieurs bandes** : grave N bandes côte à côte (espacées de 5 mm par défaut), une par **vitesse** (de la première à la dernière, interpolées), chacune étiquetée de sa vitesse — tous les niveaux de gris/noir en un seul job, sans relancer une bande par vitesse.
- **Test des offsets X/Y du laser** : job **mixte fraise + laser** qui fraise une croix centrée sur X0 Y0 puis grave une croix laser au même X0 Y0 programmé — l'écart mesuré entre les deux croix donne directement la correction des offsets X/Y de l'outil laser dans `tool.tbl` (X_nouveau = X_actuel − dX, idem Y). Seul mode de l'atelier à faire ses propres changements d'outil (`T<fraise> M6` puis `T<laser> M6`, glissière laser montée pendant la pause du second) ; les autres modes supposent le `T<laser> M6` déjà fait.

**Assemblage**
- **Job combiné** : assemble plusieurs opérations dans un seul fichier G-code avec un seul armement du laser, transition de sécurité anti-collision entre opérations. On **ajoute chaque opération depuis son vrai mode** : tu ouvres le mode normal (Découpe, Marquage, Gravure remplie, Grille de test…), tu règles tout avec **toutes ses options** (attaches, amorce, copies, styles de trait, compensation de kerf…), puis tu cliques **« ➕ Ajouter au job combiné »** ; le mode Job combiné ne fait plus qu'ordonner la liste et générer le fichier. Pas de fenêtre simplifiée à part — c'est la même fenêtre que d'habitude, donc aucune perte de fonctionnalité.

**Nuancier matériau** : la palette de gris **mesurée** d'un matériau — chaque ton = un réglage (puissance, vitesse, défocus) + son résultat constaté sur chute (noirceur 0-100 % à l'œil, largeur du trait). On l'alimente après les grilles/rampes de test (mode Nuancier, dans Tests & calibration) ; la planche peut se graver **par bande de noirceur** pour n'essayer qu'une tranche sur une petite chute. Graver la planche dépose une **fiche de disposition** (quel ton occupe quel cercle), si bien qu'on applique ensuite un réglage en **cliquant son cercle sur la photo réelle** — c'est le geste le plus fréquent. Dans les modes **Marquage** et **Gravure remplie**, choisir un ton du nuancier l'applique aussitôt : puissance/vitesse (et style Défocus à la largeur mesurée, le cas échéant) réglés sur un rendu déjà validé. La noirceur n'étant pas linéaire avec la puissance, le logiciel s'appuie sur ces mesures (ton le plus proche) plutôt que sur un modèle — fondation des futurs dégradés calibrés et photos calibrées. Le Marquage propose en plus un **ton sur mesure interpolé** : on choisit la **largeur de trait** (→ défocus via la calibration du point) et la **noirceur visée** (→ vitesse, interpolée sur la courbe noirceur→fluence construite à partir des tons **mesurés** en défocus, lissée par régression isotone car la noirceur sature avec l'énergie ; bornée aux noirceurs mesurées, jamais extrapolée) — un clic règle style Défocus + largeur + vitesse, à valider sur une chute.

Les cinq modes qui travaillent sur une **sélection** (Hachures, Gravure remplie, Marquage, Découpe plate et Découpe courbe) portent un bouton **« Reprendre la sélection de la vue »** : un panneau ne capture la sélection qu'à son *ouverture*, ce bouton la relit. Depuis la v2.10 une ligne d'état l'accompagne — grise « identique à celle du panneau » (bouton inactif), rouge « *N* objets — différente » dès que la vue 3D montre autre chose, et le bouton s'active. **Les réglages en cours ne sont jamais remplacés**, seule la géométrie change : c'est pourquoi la reprise reste un bouton et non un automatisme, une reprise automatique rechargeant aussi la recette attachée à la forme et écrasant en silence ce qu'on vient de saisir.

Tous les modes de **test & calibration** (Grille, Rampe, Bande de calibration défocus, Kerf, Offsets) ont un sélecteur de **préréglages** : des **préréglages d'usine** (★, points de départ prêts à l'emploi, non supprimables) qu'on charge d'un clic, plus les siens (sauvegarde/suppression comme les préréglages matériau des autres modes).

Communs à tous les modes : estimation de durée **tenant compte des accélérations** (profil trapézoïdal par course, accélération réglable dans les Préférences — décisif sur les remplissages faits de milliers de traits courts), aperçu de trajet dans la vue 3D, aperçu de cadrage en fichier séparé (avec faisceau de visée à très faible puissance optionnel) pour vérifier le positionnement avant de lancer, préréglages matériau, préférences globales, et **mémorisation des derniers réglages** de chaque panneau (rouvrir un mode retrouve les valeurs de la dernière fois). Mieux : les **réglages sont attachés à la forme** — à la génération, les réglages du panneau sont écrits dans une propriété de l'objet sélectionné, sauvegardée **avec le document** (.FCStd). Rouvrir plus tard le même mode avec cette forme sélectionnée re-propose *ses* réglages (prioritaires sur les derniers réglages globaux) : chaque forme du document garde sa recette de gravure. Et chaque génération crée un objet **Job** dans l'arborescence (« Job Marquage - Logo »…) qui référence la ou les formes sources : **double-clic dessus** = re-sélection des sources et réouverture du panneau pré-rempli, prêt à modifier et régénérer. Un Job par couple mode/forme — et même **par sous-sélection** : deux faces d'un même sketch ou d'un SVG importé peuvent porter deux recettes et deux Jobs distincts (« Job Gravure remplie - Sketch [Face2] »), sans rien séparer à la main. Régénérer met à jour le Job existant, votre renommage est conservé. Jobs et formes sources sont rangés automatiquement dans un dossier **« Atelier Laser »** de l'arborescence, et un bouton dédié empile les **Jobs sélectionnés dans le job combiné** (chacun avec sa recette) pour générer un fichier unique sans rouvrir les panneaux.

## La hiérarchie des tests (nouveau matériau = trois planches)

Chaque test alimente le suivant — dans l'ordre :

1. **Une fois par laser** (pas par matériau) : **Bande de calibration défocus** (deux mesures du point → Préférences), puis **Test offsets fraise + laser** (X/Y du laser dans `tool.tbl`).

2. **Nouveau matériau** : trois boutons **« Planche 1 / 2 / 3 »** (panneau Grille de test, ou l'**Assistant matériau** qui regroupe planches, saisie et déductions dans un seul panneau) → trois G-codes séparés, chacun recadré au zéro pièce.

   | Planche | Ce qu'elle grave | Ce qu'on en tire |
   |---|---|---|
   | **1 — Foyer** | une grille de traits S × F, au foyer | la **largeur brûlée** de chaque trait. Un trait resté **vierge** est une donnée, pas un raté : c'est le seuil du matériau |
   | **2 — Défocus** | la même grille, à chaque niveau de défocus | la largeur en défocus. Un niveau ne sert d'ancrage que s'il porte **au moins deux puissances** — une mesure unique rendrait la même largeur à S200 et à S1000 |
   | **3 — Point** | la bande de calibration du point | Ø au foyer + Ø à une hauteur connue → le cône. Elle est **par laser**, pas par matériau |

   Les planches 1 et 2 portent une **mire gravée** : une réglette au millimètre et quatre repères en croix aux coins d'un rectangle aux cotes rondes, annoncées dans l'en-tête du G-code. Gravée plutôt que posée — une réglette d'acier est 0,5 à 1 mm au-dessus de la surface, donc vue sous un autre angle en macro. Quatre repères et non un, pour corriger la **perspective** et pas seulement l'échelle. Le **laser** et le **régime** (`FOYER`, `DEFOCUS 15.34 PT1.18`) y sont gravés aussi : le nom de fichier ne suit pas le bois, c'est le bois qui survit.

3. **Mesurer, sur la photo** : le bouton « **Redresser une photo de planche…** » enchaîne tout — choix des photos, confirmation des cotes de la mire, clic des 4 croix, rangement dans les photos du résultat, et **pose de l'image dans le document à sa taille exacte en mm**. Le redressement tourne avec le python **système** (OpenCV est absent de l'AppImage FreeCAD), sous-traité par `subprocess` : zéro dépendance ajoutée au workbench.

   - **L'échelle est vérifiée indépendamment.** Après redressement, l'outil mesure le **pas de la réglette gravée** et le compare à l'échelle annoncée. Cette mesure n'entre pas dans l'homographie, donc elle ne relit pas ses propres données — au-delà de **1,5 %** d'écart, aucun fichier n'est écrit.
   - **Les largeurs se mesurent à la ligne**, sur le profil **moyenné** du trait (incertitude divisée par ~7 par rapport à une lecture colonne), cases enchaînées sans fermer la fenêtre, **cadrage automatique** sur les planches 1, 2 et 2b — la mise en page est rejouée depuis le code qui l'a gravée, on ne fait plus que valider. Bouton « Pas de valeur » pour une case illisible, à distinguer d'un trait **vierge**, qui est une mesure : saisir 0.
   - **La noirceur se lit d'un coup** sur toute une grille de tons : la gravure dépose une **fiche de grille** (position de chaque case dans le repère de la mire), deux repères *bois nu / noir max* proposés puis déplaçables (le pourcentage est **relatif**, donc insensible à l'éclairage), et un **plancher de bruit mesuré sur le grain** — une case sous ce bruit n'est pas un ton clair, elle est vide.
   - **Les planches redressées ont leur dossier** (`planches_dir`, défaut `~/Planches-LaserAtelier`), nommées `<laser>_<planche>_<date>_redresse` plus un nom libre. Le laser dans le nom n'est pas de l'étiquetage : une largeur brûlée **n'a de sens que pour le module qui l'a gravée** — et à l'inverse, quelqu'un ayant le *même* module peut reprendre ces mesures sans refaire une heure d'établi. Un bouton liste, compare (dont l'écart mesuré sur la réglette) et **supprime tous les fichiers** d'une planche, pas seulement l'aperçu.

   Les largeurs se saisissent dans « **② Entrer les mesures** » du panneau Grille de test, une grille par planche et par niveau.

4. **Après le nuancier** (facultatif, pour choisir à l'œil) : **Mire des styles** (Marquage) et **Mire des tramages** (Gravure photo).

## Modèle de défocus (remplissage noir)

Pour noircir une surface en un seul passage, le remplissage éloigne le bec du foyer : le point s'élargit et des hachures espacées se recouvrent. Le modèle est un cône de divergence linéaire calibré à partir de **deux mesures réelles** du point (au foyer, puis à un défocus connu) — jamais deviné. La **Bande de calibration défocus** fournit ces mesures ; on les saisit **une seule fois dans la section « ② Entrer les mesures »** de son panneau (« point au foyer », « défocus de test », « point au défocus de test ») et tous les modes concernés (Hachures 2D, Gravure remplie, Grille de test, style Vague) les réutilisent : l'atelier calcule le défocus nécessaire pour un espacement donné (et rentre le remplissage du rayon de point pour rester dans le contour).

### Puissance vs défocus (fluence)

Défocaliser étale la **même** puissance sur un point plus large : l'énergie déposée par unité de surface (la **fluence**) baisse, et sous un seuil le trait ne marque plus. Pour un trait balayé à la vitesse `v`, avec un point de diamètre `d` et une puissance `P`, la fluence vaut `F ∝ P / (d · v)` (l'aire du point grossit en `d²`, mais le temps de séjour sur chaque point grossit en `d`, d'où le `1/d` net). Les modes **Gravure remplie** et **Marquage (style Défocus)** exposent une section « Puissance vs défocus » : on renseigne un réglage de **référence** connu bon sur le matériau (puissance, vitesse, et **largeur de point** d'une gravure réussie), et l'atelier soit **indique** la fluence obtenue par rapport à cette référence (à ajuster à la main), soit **compense la puissance automatiquement** pour retrouver la même fluence à la largeur de point et à la vitesse courantes (case à cocher). Dans le mode Marquage, on saisit d'ailleurs directement la **largeur du point** voulue (l'atelier en déduit la hauteur de défocus via la calibration), plus intuitif que de régler une remontée de bec. Aucune constante optique absolue n'est supposée — seuls des rapports à un point mesuré, dans l'esprit « on mesure, on ne devine pas » du reste de l'atelier.

## Démo vidéo

[Vidéo de démonstration sur YouTube](https://youtu.be/KP4F4Cd287A)

## Captures d'écran

Chaque panneau de l'atelier est présenté (capture complète) dans la **[galerie des panneaux](docs/panneaux.md)**.

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

Si ton laser a un nez de géométrie différente, **le contrôle anti-collision doit être adapté avant d'utiliser les modes sur surface courbe** — sinon il sous-estimera (ou surestimera) les collisions. Pas besoin de toucher au code : le profil du bec s'édite depuis le panneau **Préférences** de l'atelier (icône engrenage), ou à la main via la clé `nozzle` du fichier de configuration `laser_atelier_config.json` (dossier de configuration utilisateur de FreeCAD) :

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
  en-tête `G21`/`G90`/`G94`/`G43 H<outil laser>`, armement unique par `M3 $1`
  (faisceau à zéro), puissance par segment `S… $1`, `S0 $1` sur les
  rapides, désarmement `M5 $1`, arrêt de job propre au `M2`
- **Prérequis machine avant de lancer un fichier généré** : avoir fait
  `T<outil laser> M6` dans la session LinuxCNC (T100 par défaut,
  réglable en Préférences). Le `G43 H<outil laser>` de l'en-tête
  applique les offsets X/Y et le Z palpé de l'outil laser à ce
  moment-là ; sans lui, les coordonnées seraient interprétées en
  position broche et non nez laser (focus faux, X/Y décalés). Le
  prérequis est rappelé en commentaire dans chaque fichier généré.
- Le sélecteur multi-broche `$1` et la compensation d'outil sont pensés
  pour LinuxCNC (laser = spindle 1, outil T100 par défaut). Le sélecteur
  broche, le numéro d'outil laser et l'échelle de puissance S se changent
  dans les Préférences de l'atelier
- **Contrôleur GRBL** : choisir le dialecte **GRBL** dans les Préférences
  (réglé par profil laser — créer un profil par machine). Le G-code généré
  est alors du GRBL 1.1 pur : pas de sélecteur de broche ni de `T`/`M6`/`G43`,
  pas de `G64` (le lissage de trajectoire est natif chez GRBL, réglé par la
  junction deviation `$11`), armement en `M4` (mode laser). Côté machine :
  activer le mode laser `$32=1` et régler `$30` à la même valeur que
  l'Échelle de puissance max des Préférences (1000 par défaut). Le zéro Z se
  pose sur la surface à graver par le moyen de son choix (cale, réglet à la
  hauteur de focale…) — **aucun palpeur n'est requis**. Le Test des offsets
  X/Y (job mixte fraise+laser) reste propre à LinuxCNC.
- **Contrôleur grblHAL** : dialecte **grblHAL** — comme GRBL (`M4`, pas de
  sélecteur de broche ni de `G64`), mais **avec** le changement d'outil et la
  compensation `T`/`M6` + `G43 H` comme LinuxCNC. Nécessite un firmware
  compilé avec la table d'outils (option `N_TOOLS`) ; le numéro d'outil laser
  des Préférences est alors utilisé.
- **Surface de travail de la machine** : renseigner **« Surface de travail (X × Y) »** dans les
  Préférences (par profil laser). À l'écriture d'un fichier, l'atelier compare l'emprise réelle du
  parcours — cadrage et marges de survol compris, après recadrage au zéro pièce — et **prévient** si
  ça ne tient pas, en donnant les cotes. La position compte autant que la taille : un motif de
  100 × 100 tient dans 400 × 415, pas s'il est posé à X350. Laisser sur « inconnue » (0) désactive
  le contrôle. Sur une machine GRBL, `$130`/`$131` donnent la course exacte.
- **Graveur de table SANS AXE Z** (Creality Falcon, Ortur, xTool… : mise au
  point manuelle en tournant la lentille) : cocher **Machine sans axe Z** dans
  les Préférences (réglé **par profil laser**, comme le dialecte). Aucun mot
  `Z` n'est alors écrit, et les mouvements qui n'étaient que du Z
  disparaissent. C'est nécessaire : **tout** fichier produit ici porte des Z,
  y compris un marquage à plat avec le Z de travail et le survol à zéro — au
  minimum la hauteur de sécurité de début et de fin. Sans axe Z, le contrôleur
  accepte le mot, croit déplacer un axe absent, y passe du temps, et lève une
  alarme de limite logicielle si `$20=1` (course Z nulle).
  ⚠️ **Ce que ça coûte** : tout ce qui repose sur le défocus devient
  impossible — calibration défocus (planches 2 et 2b), nuancier aux niveaux de
  défocus, fuseau Z, suivi de surface courbe, style « vague ». Ces modes ne
  sont pas refusés : l'atelier écrit dans l'en-tête du fichier **et** dans la
  console combien de mouvements *gravés* changeaient de hauteur, parce qu'un
  tel job ne gravera pas ce qui a été calculé. Restent utilisables au foyer :
  marquage, découpe, gravure remplie, similigravure et les tramages photo,
  grille de test, polices, import SVG/LightBurn.
- ⚠️ **Les dialectes GRBL et grblHAL n'ont jamais fait tourner une ligne sur
  une machine réelle** (la machine de développement tourne sous LinuxCNC).
  Ce qui EST garanti, et vérifié à chaque exécution des tests
  (`tests/test_dialectes.py`, quatre familles de jobs) : aucune commande
  inconnue de GRBL (ni `M67`/`M68`, ni `G64`, ni `G10`, ni sélecteur `$n`) ;
  tout en ASCII ; aucune ligne au-delà des 128 octets du tampon de réception
  de GRBL (la plus longue mesurée : 86 caractères) ; `M4`/`M5`/`M2` présents ;
  grblHAL qui garde sa table d'outils là où GRBL la commente.
  Reste à vérifier sur une vraie carte : que le contrôleur accepte le fichier,
  que le laser tire à la bonne puissance, et que `$32=1` + `$30` suffisent.
  Retours bienvenus via les issues GitHub.
- ⚠️ **Densité des jobs photo sur GRBL** : un portrait de 120 × 180 mm au pas
  0,30 fait ~172 000 blocs pour près de 6 Mo. Une carte alimentée *en série*
  devient le goulot d'étranglement ; celles qui lisent une carte SD ou du WiFi
  (ESP32) n'ont pas ce souci. Dans le doute, privilégier les modes
  géométriques ou un pas de trame plus grand.

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

### Préférences de l'atelier (icône engrenage)

Les réglages généraux de l'atelier s'éditent depuis la commande **Préférences** (barre d'outils / menu "Atelier Laser"). Ils sont enregistrés dans le même `laser_atelier_config.json` (clé `settings`, clé `nozzle` pour le profil du bec) et appliqués immédiatement, sans redémarrer FreeCAD :

| Réglage | Clé JSON | Défaut | Rôle |
|---|---|---|---|
| **Puissance par M67** | `settings.puissance_par_m67` | `False` | **Le réglage qui change le plus de choses.** Coché, la puissance voyage par `M67 E0 Q<v>` — une sortie **synchronisée avec le mouvement** — au lieu du mot `S`. Sous LinuxCNC, un `S` entre deux `G1` **arrête la machine** (mesuré : 76 ms par bloc contre 22,5), ce qui saccade tous les tramages modulés et les rallonge d'un facteur ~3. Sans effet en GRBL/grblHAL, qui ignorent `M67` et n'ont pas le problème (mode laser `$32=1`). Nécessite un `sum2` HAL additionnant `spindle.N.speed-out` et `motion.analog-out-00` |
| Dialecte G-code | `settings.gcode_dialect` | `linuxcnc` | `linuxcnc`, `grbl` ou `grblhal`. Réglé **par profil laser**. Détermine le sélecteur de broche, `G64`, la compensation d'outil et la commande d'armement |
| Recadrer au zéro pièce | `settings.gcode_origin_bbox` | `True` | Translate le G-code pour que le coin de la boîte englobante tombe en (0, 0) |
| Sections repliables | `settings.sections_accordeon` | `True` | Les sections des panneaux se replient/déplient, et leur état est mémorisé |
| G-code perso avant / après | `settings.gcode_pre_global`, `settings.gcode_post_global` | `""` | Lignes injectées en tête et en pied de **tous** les jobs (aspiration, air assist…) |
| Étiquettes gravées : S / F | `settings.label_power`, `settings.label_feed` | `600` / `800` | Puissance et vitesse des chiffres gravés sur les planches de calibration — assez pour être lisibles, pas assez pour brûler la case voisine |
| Dossier G-code | `settings.gcode_dir` | `/mnt/srv-partage/Gcode` | Dossier proposé par défaut à la sauvegarde G-code de tous les modes (repli sur `/tmp` s'il n'est pas accessible — partage réseau non monté...) |
| Vitesse rapide (estimation) | `settings.rapid_feed_mm_min` | `6000` | Vitesse G0 supposée pour l'estimation de durée des jobs. N'affecte **que** l'estimation, jamais le G-code généré. Mettre la `MAX_VELOCITY` de la machine pour des estimations réalistes |
| Marge de survol (transits) | `settings.travel_clearance_mm` | `10.0` | Marge ajoutée au Z de travail pour les déplacements à vide et le début/fin de job (modes Grille de test et Découpe à plat — les modes courbes ont leur champ Marge de sécurité par panneau). `0` = transits au Z de travail |
| Puissance de cadrage (S) | `settings.frame_power` | `0` | Puissance du faisceau pendant l'aperçu cadrage, pour visualiser la zone de travail sur la pièce. `0` = laser éteint. Sinon **très faible** (S5–S20 typiquement) : juste de quoi voir le point sans marquer — à valider sur une chute |
| Vitesse de cadrage | `settings.frame_feed_mm_min` | `1500` | Vitesse du tracé de cadrage quand le faisceau de visée est allumé (sans effet à puissance 0 : le tracé se fait en rapides G0) |
| Vitesse Z max (avertissement) | `settings.z_max_feed_mm_min` | `1500` | Vitesse max supposée de l'axe Z — sert uniquement à avertir quand un trait en **vague défocus** demanderait plus vite (le trajet serait ralenti par la machine). N'affecte jamais le G-code |
| Accélération (estimation) | `settings.accel_mm_s2` | `600` | Accélération machine supposée pour l'estimation de durée (mettre la `MAX_ACCELERATION` X/Y du LinuxCNC). N'affecte jamais le G-code |
| Point au foyer | `settings.spot_focus_mm` | `0.15` | **Calibration du point** (mesurée avec la Bande de calibration défocus) : diamètre du point au foyer. Utilisée par tous les modes à défocus — plus rien à resaisir dans les panneaux |
| Défocus de test | `settings.spot_test_defocus_mm` | `3.0` | Calibration du point : hauteur au-dessus du foyer de la 2e mesure |
| Point au défocus de test | `settings.spot_test_diameter_mm` | `1.0` | Calibration du point : diamètre mesuré à ce défocus |
| Z de travail (foyer) par défaut | `settings.z_work_mm` | `8.0` | Z de travail **proposé par défaut** dans tous les panneaux (= focale du nez avec le zéro Z sur la surface). Chaque panneau reste modifiable et retient sa dernière valeur |
| Marge de survol (marquage) par défaut | `settings.transit_margin_mm` | `0.5` | Marge de transit proposée par défaut dans les modes de marquage (`0` recommandé sur pièce plate) |
| Sélecteur broche | `settings.spindle_select` | `$1` | Sélecteur multi-broche ajouté aux commandes `S`/`M3`/`M5` (LinuxCNC : laser = spindle 1) |
| Numéro d'outil laser | `settings.laser_tool` | `100` | Numéro (tool.tbl) de l'outil laser : compensation `G43 H<n>` en tête de job (prérequis `T<n> M6`) et Test des offsets X/Y |
| Échelle de puissance max (S) | `settings.s_max` | `1000` | Valeur `S` correspondant à la pleine puissance de la broche laser (config LinuxCNC). Fixe le maximum des champs de puissance et le plafond de la compensation de fluence |
| Temporisation d'armement | `settings.arm_dwell_s` | `2.0` | Pause `G4` après l'armement (`M3` à puissance nulle), le temps que l'électronique du module soit prête |
| Hauteur bec minimale | `settings.safe_min_nozzle_height_mm` | `1.5` | Butée de sécurité : le bec ne descend jamais plus près de la surface, quelle que soit la passe — garde-fou anti-collision |
| Épaisseur max sans avertir | `settings.max_thickness_warning_mm` | `12.0` | Au-delà, avertissement à la génération d'une découpe (n'empêche pas de générer) |
| Pas Z max sans avertir | `settings.recommended_max_step_mm` | `1.5` | Au-delà, avertissement à la génération (pas trop grand = parois du trait qui font écran au faisceau) |
| Bec : diamètres et hauteur | `nozzle.bottom_diameter_mm`, `nozzle.top_diameter_mm`, `nozzle.height_mm` | `5` / `16` / `18` | Profil du bec pour le contrôle anti-collision des modes sur surface courbe (voir « Adapter à un autre laser ») |

Une valeur invalide dans le JSON (nombre négatif, chaîne vide...) est ignorée avec un avertissement dans la vue Rapport, et la valeur par défaut est conservée.

### Profils laser (plusieurs modules)

Si tu montes plus d'un module laser sur la machine (par ex. un module bleu 450 nm en `T100` pour le bois et un **module IR 1064 nm** en `T101` pour marquer le métal), chacun a besoin de sa propre calibration. La section **Laser actif** en tête des Préférences gère ça : un sélecteur de **profils laser** nommés, avec **Nouveau (cloner)**, **Renommer** et **Supprimer**. Changer de laser applique aussitôt son profil.

Chaque profil porte les réglages **propres au module** (les autres restant communs à la machine) :

| Par laser (profil) | Commun (machine) |
|---|---|
| `laser_tool`, `s_max`, `frame_power`, la **calibration du point** (`spot_focus_mm`, `spot_test_defocus_mm`, `spot_test_diameter_mm`), le **Z de travail** (`z_work_mm`), le **profil du bec** (`nozzle`) — **et les DONNÉES** : `nuancier`, `burn_widths` et tous les blocs `presets_*` | dossier G-code, sélecteur broche, cinématique (rapide/accél/Z max), marges et garde-fous de sécurité |

Dans la config JSON : les profils sont dans `lasers` (`{"<id>": {"name", "settings", "nozzle"}}`) et le profil courant dans `active_laser` ; les clés `settings`/`nozzle` reflètent en permanence le laser actif (le reste du code les lit sans changement). Au premier lancement, un profil **« Bleu 450 nm »** est créé automatiquement à partir des réglages existants.

Le **nuancier, les largeurs brûlées et les préréglages matériau sont eux aussi rangés par profil** : un bleu 450 nm et un IR 1064 nm ne partagent ni gris, ni largeurs, ni couples puissance/vitesse pour un même bois. Ils restent recopiés au niveau supérieur de la config, si bien que tout le code de lecture est inchangé, et changer de laser les bascule d'un bloc. **Conséquence à connaître : un laser fraîchement cloné démarre avec un nuancier, des largeurs et des préréglages VIDES** — c'est voulu, il n'a encore rien mesuré.

### Constantes avancées (code uniquement)

Quelques constantes restent volontairement dans le code (`laser_core.py`) — les changer sans comprendre leur rôle peut produire du G-code faux ou lent :

| Constante | Défaut | Rôle |
|---|---|---|
| `cmd_tool_comp()` | `G43 H<outil laser> (...)` | Ligne de compensation d'outil en tête de chaque job (offsets X/Y + Z palpé de l'outil laser des Préférences). Omise automatiquement en dialecte GRBL (Préférences) |
| `FOCUS_TABLE` | `{2: 7, 3: 7, ...}` | Tableau constructeur épaisseur (mm) → hauteur de bec (mm) pour la découpe à plat (LT-80W). À refaire pour un autre module laser |
| `CHAIN_TOLERANCE` | `0.001` mm | Tolérance de jonction entre segments pour le chaînage des contours |
| `DISCRETIZE_DISTANCE` | `0.3` mm | Résolution de discrétisation des tracés (plus petit = plus fidèle mais G-code plus gros) |
| `TRANSIT_SAMPLE_STEP` | `2.0` mm | Résolution du suivi de courbure pendant les transits (mode courbe) |
| `MESH_PROBE_DEVIATION_MM` | `0.05` mm | Écart max entre le maillage de sonde et la vraie surface (modes courbes) |
| `NOZZLE_CHECK_INTERVAL_MM` | `1.5` mm | Espacement minimal entre deux contrôles de dégagement du bec |
