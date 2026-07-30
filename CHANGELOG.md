# Journal des versions

Ce journal commence à la **v2.0.0**. Pour tout ce qui précède, `git log
--oneline` est la source de vérité — chaque message de commit y raconte le
pourquoi, souvent avec les chiffres mesurés qui l'ont motivé.

Les versions suivent `MAJEURE.MINEURE.CORRECTIF`. `VERSION` dans
`laser_core.py` est la source unique ; elle est bumpée en même temps que
`package.xml`, le badge de `docs/index.html`, le `README` et `docs/manuel.html`
(+ régénération du PDF), dans un seul commit.

---

## v2.2.2 — 30 juillet 2026

### Corrigé

**La table des largeurs libres était en écriture seule.** Christophe a saisi
ses cinq relevés de rampe, a voulu les corriger — et la table était vide. Son
`reload()` ne faisait qu'effacer le message ; rien ne réaffichait jamais
l'existant. Une mesure qu'on ne peut pas relire ne peut pas être vérifiée, et
c'est la donnée la plus chère du projet.

Elle réaffiche maintenant les points **hors grille** déjà enregistrés pour le
matériau — et seulement ceux-là : les autres appartiennent à la grille de la
Planche 2, qui les montre déjà et sait les corriger. Les rendre modifiables
aux deux endroits ferait deux vérités pour une mesure.

**Vider une ligne supprime la mesure**, ce qui manquait aussi : sans ça,
corriger le DÉFOCUS d'un point en créait un second au lieu de le déplacer. La
suppression ne porte que sur les points que la table a réellement AFFICHÉS —
jamais sur une mesure restée invisible.

Après enregistrement, la table se recharge : elle montre l'état réel de la
table, pas la saisie qu'on vient de taper.

Le test a lui-même dû être corrigé deux fois, et chaque correction disait
quelque chose : il écrivait en ligne 0 (écrasant les points désormais
réaffichés — le comportement était juste, le test naïf), et il comptait des
points au lieu de raisonner en ensembles, ce qui échouait dès que les relevés
étaient déjà enregistrés. Il vérifie maintenant qu'aucune mesure existante ne
disparaît, quel que soit l'état de départ.

---

## v2.2.1 — 30 juillet 2026

### Corrigé

**L'avertissement d'arrondi du défocus était incompréhensible.** Il disait
« seront relus au niveau standard le plus proche (36) ». Christophe n'a pas
compris, et il avait raison : « niveau standard » n'est expliqué nulle part
dans l'interface, et « relu » décrit un détail d'implémentation, pas ce qui
arrive à sa mesure.

Reformulé en CONSÉQUENCE : « le défocus 40 mm comptera comme 36 mm. L'atelier
regroupe les mesures en défocus autour de hauteurs de référence (15, 36) et y
rattache tout ce qui en est à moins de 5 mm. La mesure reste juste, mais elle
servira comme si elle avait été faite à cette hauteur — saisir cette valeur
directement revient au même. »

Un message que l'utilisateur ne comprend pas ne l'avertit de rien.

---

## v2.2.0 — 30 juillet 2026

### Ajouté

**Saisie LIBRE des largeurs brûlées**, dans le ② du panneau Rampe
puissance/vitesse : une table (puissance, vitesse, défocus, largeur) sans
grille imposée, à côté du « + Ajouter ce ton » déjà présent. L'un enregistre le
ton que rend le bois, l'autre l'épaisseur que brûle le laser — la rampe donne
les deux, et jusqu'ici seule la première avait où aller.

La grille de saisie existante est le MIROIR de la Planche 2 : puissances
1000..200, vitesses 200..800, défocus 15 et 36. Juste pour une planche, qui
grave une grille discrète. Mais la rampe mesure un CONTINUUM — la puissance et
la hauteur montent ensemble le long de chaque ligne. La première rampe Z gravée
a donné cinq points du genre **S980 / F200 / défocus 60 / 4,00 mm** : aucun
n'entrait dans la grille, et il n'existait nulle part où les mettre.

Ces mesures étendent la couverture bien au-delà de ce qui existait (rien
n'allait plus loin que défocus 36), ce qui sert directement aux traits épais
décoratifs, du foyer au grand défocus.

Deux précautions, chacune payée par une leçon de ce projet :

- **Fusion, jamais remplacement.** `save_burn_widths` écrase la table du
  matériau : on relit l'existant et on ne remplace que les points de même
  (S, F, défocus). Un enregistrement ne doit jamais faire disparaître des
  heures de pied à coulisse — c'est la donnée la plus irremplaçable du projet.
- **Lecture brute de la config** pour fusionner, pas via `load_burn_widths`,
  qui ramène les défocus au niveau standard proche : passer par elle
  réécrirait les valeurs déjà stockées au passage.

Et le défocus saisi n'est pas arrondi en silence. À moins de 5 mm d'un niveau
standard il sera relu là (un **40 devient 36**) : la table le dit après
l'enregistrement, en rouge, avec les valeurs concernées. Une valeur tapée à la
main est délibérée — elle mérite qu'on prévienne plutôt qu'on corrige.

`tests/test_largeurs_libres.py` prouve d'abord qu'aucun des cinq relevés
n'entre dans la grille figée (plutôt que de l'affirmer), puis que la fusion
n'efface rien, que les défocus exacts sont conservés, qu'un second
enregistrement remplace au lieu de dupliquer, que le 40 est bien relu en 36, et
qu'une ligne incomplète est ignorée sans rien deviner.

---

## v2.1.2 — 30 juillet 2026

### Corrigé

**Le désarmement GRBL portait un `M67`**, commande que GRBL ne connaît pas :
chaque job y aurait fini sur une erreur. La ligne venait d'être ajoutée UNE
HEURE plus tôt (v2.1.1) au désarmement PARTAGÉ entre dialectes, pour neutraliser
le canal de puissance sous LinuxCNC. Rien ne l'aurait signalé — aucune machine
GRBL n'avait jamais lancé une ligne de cet atelier.

Trouvé en relisant, pour la première fois, ce que le dialecte GRBL émet
vraiment. Le reste de cette relecture est rassurant : aucun `$n`, aucun
`T`/`M6`/`G43`, aucun `G64`, tout en ASCII, et la ligne la plus longue fait
86 caractères — bien sous le tampon de réception de 128 octets de GRBL.

### Ajouté

`tests/test_dialectes.py` fige ce contrôle. Il ne prétend pas que GRBL
« marche » — seule une machine le dira. Il vérifie ce qui est vérifiable ici :
qu'aucune commande inconnue du contrôleur visé n'est émise (M67/M68, G64, G10,
`$n`), que tout est ASCII, qu'aucune ligne ne dépasse le tampon GRBL, que
l'armement en mode laser (`M4`) et la fin de programme sont bien là — et que
grblHAL garde sa table d'outils là où GRBL la commente. Le réglage
« Puissance par M67 » est demandé explicitement dans le test : un dialecte qui
ne connaît pas M67 doit l'ignorer, pas compter sur une case décochée.

---

## v2.1.1 — 30 juillet 2026

### Corrigé

**Chaque job neutralise maintenant LES DEUX canaux de puissance à
l'armement**, pas seulement le sien. Trouvé en répondant à une question de
Christophe (« ces G-codes ne sont plus bons ? »), pas par un test.

Le HAL additionne `spindle.1.speed-out` et `motion.analog-out-00`, ce qui permet
de basculer le réglage sans recâbler. Mais **les deux canaux persistent** : un
job interrompu en plein vol laisse SA valeur en place. Un job M67 avorté à Q600,
suivi d'un job en `S` direct, aurait donc gravé à `S+600` partout — trop fort,
et sans un mot. La réciproque était vraie aussi.

L'armement et le désarmement des deux modes sont désormais rigoureusement
identiques et remettent les deux canaux à zéro. Le test dit exactement ce qu'il
garantit : aucune PUISSANCE ne voyage par le mot `S` en mode M67 — pas de `S`
sur un mouvement, et un `S` isolé ne peut valoir que 0. Formuler « aucun mot
`S` » aurait été plus court et faux.

Les G-codes déjà écrits en `S` direct restent valides ; c'est précisément ce que
la somme garantit. Ils n'ont simplement pas la ligne de neutralisation : après
un job M67 interrompu, les régénérer (ou passer un `M67 E0 Q0` en MDI) est plus
sûr.

---

## v2.1.0 — 30 juillet 2026

### Ajouté

**La puissance peut passer par `M67` au lieu du mot `S`** (case « Puissance par
M67 » des Préférences, LinuxCNC seulement, réglage machine-GLOBAL et non par
profil laser : c'est le câblage HAL qui décide, et il est commun aux deux têtes). Gain attendu **~3x sur tout tramage
qui module la puissance**, donc sur les jobs les plus longs.

Le fait établi, et il l'est par l'expérience : **sur la PrintNC, un mot `S`
entre deux G1 arrête le mouvement**, même sur des segments parfaitement
colinéaires. Deux fichiers de géométrie rigoureusement identique (200 segments
de 0,30 mm à F800, laser désarmé) ont tranché à l'oreille — `S` constant
fluide, `S` variable saccadé. Ils restent sur le partage sous
`test_accoup_S_{constant,variable}.ngc` pour revérifier si la config machine
bouge.

`M67 E0 Q<v>` est la sortie analogique **synchronisée avec le mouvement** : la
valeur est appliquée au début du bloc suivant sans vider la file de
trajectoire. (`M68` est la variante immédiate, et elle arrête le mouvement.)
On garde un escalier de puissance, un palier par segment, mais plus d'arrêt
entre les paliers.

Onze points d'émission convertis dans six familles de générateurs, **tous
ensemble** : le câblage machine étant commun, un générateur resté en `S` alors
que la machine écoute l'autre canal graverait blanc, sans erreur, pendant des
heures. Côté HAL, un `sum2` **additionne les deux sources** (l'une vaut toujours
zéro) : les deux modes fonctionnent, les anciens `.ngc` restent valides, et il
n'y a aucun basculement coordonné à orchestrer.

**GRBL et grblHAL ne sont pas concernés, et ce n'est pas une limitation.**
`M67` est un code LinuxCNC. Mais le mode laser de GRBL (`$32=1`, armement `M4`)
traverse les `G1` consécutifs sans s'arrêter quand seule la puissance change :
il résout la même difficulté autrement. La case est donc ignorée sur ces
dialectes, comme le vérifie le test.

**Confusion de vocabulaire, à ne pas refaire** : `motion.analog-out-00` porte le
nom « analogique » dans LinuxCNC, mais c'est un simple pin numérique, et il
alimente ici le RAPPORT CYCLIQUE du PWM. L'intuition de départ — « faire varier
le PWM pendant un déplacement linéaire » — était donc juste, et formulée bien
avant qu'on trouve `M67` ; le mot « analogique » a fait croire qu'il fallait du
matériel analogique. Le PWM n'a jamais été la limite, c'est le canal du G-code
qui l'était.

Deux pistes écartées avant celle-là, chacune par la mesure : câbler
`spindle.1.at-speed`, qui n'avait jamais été relié (les à-coups ont persisté —
la ligne reste, elle est juste, elle ne réglait pas ça) ; et réduire le nombre
de niveaux de puissance pour allonger les segments (de 161 à 8 niveaux, la
longueur moyenne ne passe que de 0,36 à 0,73 mm sur une photo réelle — un
segment par pixel est structurel sur une image bruitée).

`tests/test_puissance_m67.py` tient deux promesses, et la première est la plus
importante : en mode direct la sortie est **identique au bit** (vérifié MD5
pour MD5 contre le code d'avant la conversion, sur huit générateurs) ; en mode
M67, aucun `S` ne subsiste sur un mouvement, `M3`/`M5` sont conservés (c'est
l'interlock, pas la puissance), aucun `M68` n'est émis, et la géométrie est
rigoureusement identique dans les deux modes.

---

## v2.0.1 — 30 juillet 2026

### Corrigé

**L'estimation de durée était optimiste d'un facteur 3 sur les tramages qui
modulent la puissance par pixel** — exactement les jobs les plus longs, ceux
où l'estimation sert à décider si on lance. Deux causes, toutes deux mesurées
sur un portrait en lignes gravées de 120 × 180 mm annoncé 1h30 et parti pour
4 h (172 614 blocs G1, longueur médiane 0,30 mm) :

- `ACCEL_MM_S2` valait **800** quand la machine tourne à **400**. Une donnée
  machine simplement fausse, et d'autant plus coûteuse que le job est fait de
  segments courts, là où l'accélération fait tout le temps. Elle doit valoir le
  `MAX_ACCELERATION` du `.ini` LinuxCNC.
- **Un changement de puissance rompt la course.** L'estimateur fusionnait les
  segments colinéaires de même avance, supposant que LinuxCNC les enchaîne. Le
  temps réel par bloc (~76 ms) correspond à un déplacement de 0,30 mm avec
  ARRÊT AUX DEUX BOUTS à 400 mm/s² (55 ms) : la machine ne relie pas deux
  segments dont le S diffère, même parfaitement colinéaires.

Estimation de ce portrait : 1h30 → **3h05**, contre ~4 h observées. Le reste
est du temps de traitement par bloc, non mesuré : aucune constante n'a été
inventée pour le combler. Les jobs à puissance constante (découpe, marquage,
remplissage) ne changent pas d'une seconde.

Piste explorée et écartée, mesurée : réduire le nombre de niveaux de S pour
allonger les segments. De 161 à 8 niveaux, la longueur moyenne ne passe que de
0,36 à 0,73 mm sur une photo réelle — un segment par pixel est structurel sur
une image bruitée. Le seul vrai levier reste le **pas de trame**.

---

## v2.0.0 — 30 juillet 2026

Version de consolidation. Aucune fonctionnalité spectaculaire : une passe sur
tout ce qui s'était accumulé, pour repartir sur une base propre. Elle vient
après une journée de gravures réelles, et la plupart des correctifs ci-dessous
ont été trouvés par la pièce ou par le bruit de la machine, pas par relecture.

### Corrigé

- **Gros points Z : va-et-vient en X** (v1.97.0). Le correctif de v1.93.0
  — graver le micro-trait dans le sens du serpentin — n'avait jamais été
  appliqué à `generate_gcode_photo_zdots`, qui a gardé le défaut un mois. Sur
  un portrait de 134 × 201 points : **26 600 changements de sens** et 5,3 m de
  déplacement inutile (−26 %). Le G-code était valide et l'image juste ; seul
  le bruit trahissait le défaut, et c'est ainsi que Christophe l'a retrouvé.
- **Rampe Z : les graduations chiffraient la cote machine** (v1.97.1). Avec un
  foyer à 8 mm, la planche affichait « 10 15 20 25 » pour des défocus de 2, 7,
  12 et 17. Or ce chiffre part directement dans « + Ajouter ce ton » comme
  `z_offset`, qui est un défocus : un « 15 » lu sur la planche aurait rangé une
  mesure faite à 7 mm parmi celles de 15, en silence, dans la table qui
  alimente le modèle de largeur brûlée. Graduations aux défocus **ronds**
  désormais, et c'est le défocus qui est gravé.
- **Recettes photo hors régime.** La recette calibrée MDF demandait un point
  de 0,80 mm — défocus 8,75 — quand son nuancier est mesuré à 12,20 : l'erreur
  allant comme le carré du rapport des diamètres, **1,56× de densité de
  puissance en trop**. Le `gamma 1,5` de ces recettes compensait ce mauvais
  régime au lieu de le corriger.
- **Une phrase du manuel mutilée** par un `sed` antérieur (§ Grille de test),
  présente aussi dans le PDF publié.

### Ajouté

- **Lignes gravées : la vitesse avant le pas.** Entre F800 et F1500 la plage
  de largeurs ne s'arrête pas d'un coup, elle s'effondre progressivement
  (0,23 mm à F1000 ; 0,17 à F1200). Le panneau ne refusait rien et conseillait
  de resserrer le pas — conseil exact mais calculé sur une plage déjà amputée
  par la vitesse. Il nomme maintenant la vitesse à retrouver et chiffre le
  gain, avant tout conseil sur le pas, et se tait là où ralentir ne rapporte
  rien.
- **Les tramages à grain demandent de la place.** Sous 100 mm de large, le
  grain se voit plus que le sujet. Ce n'est pas une mesure, c'est un jugement
  d'atelier — mais il vient d'une planche gravée. Rappelé sous la grille pour
  les trois tramages concernés.
- **La mire compare les sept tramages** (elle en montrait quatre), chacun dans
  **son** régime : les deux tramages à grain au foyer, les gros points Z avec
  leur Z par point, et les lignes gravées à la vitesse où leur trait enfle
  encore — sinon cette bande sortirait en aplat, ou serait sautée.
- **Six recettes photo ancrées sur une mesure**, dont quatre pour le hêtre (il
  n'y en avait aucune, alors que c'est le bois de l'atelier). Gamma à 1,0.
- Un **journal des versions** (ce fichier).

### Changé

- **Un tramage photo est une ligne de table.** Vingt tests d'index en dur
  (`if idx in (5, 6)`) étaient dispersés sur un millier de lignes : la
  connaissance d'un tramage n'était écrite nulle part, seulement recalculée
  site par site. C'est la cause commune des trois bugs livrés le 29 juillet.
  `_TRAMAGES` déclare maintenant les propriétés intrinsèques de chaque
  tramage ; tout le reste s'en déduit, et le panneau n'a plus qu'un seul
  endroit qui traduit un rang en comportement.
- **Les préréglages et réglages d'objet mémorisent des NOMS, plus des rangs**
  pour les listes qui portent une donnée textuelle (tramage, matériau) : un
  rang désignerait autre chose après une réorganisation. Les rangs déjà écrits
  dans les configs restent compris.
- **Le matériau du panneau photo est mémorisé.** Il ne l'était pas du tout,
  alors que tout le régime en dépend : une session repartait sur le premier
  matériau du nuancier sans le dire.
- **`CLAUDE.md` découpé** en 158 lignes de non-négociables + six règles
  `.claude/rules/*.md` scopées par chemin, qui se chargent quand le code
  correspondant est lu. Le fichier de 800 lignes réduisait l'adhérence, et
  surtout un `CLAUDE.md` de sous-dossier n'est pas réinjecté après une
  compaction de contexte — d'où des règles qui s'évaporaient en pleine session.

### Tests

De 3 à 7 suites (`python3 tests/lancer.py`). Les nouvelles ferment chacune la
porte d'un défaut réel de cette journée :

| Suite | Ce qu'elle interdit |
|---|---|
| `test_micro_traits` | un demi-tour en X dans une ligne, sur les **7** tramages |
| `test_rampe_z` | une graduation qui annonce un défocus qu'elle n'atteint pas |
| `test_mire` | une bande gravée hors de son régime, ou qui en recouvre une autre |
| `test_recettes_photo` | une recette calibrée hors du régime de ses propres tons |

Deux règles de méthode s'en dégagent, et valent pour la suite : **tester la
propriété sur toute la famille**, pas le cas signalé (un test écrit pour le
seul générateur réparé serait resté vert pendant le mois où son voisin portait
le même défaut) ; et **vérifier contre un fichier réellement généré** quand il
en existe un — `/mnt/srv-partage/Gcode/*.ngc` dit ce qui a tourné sur la
machine, un test qui ne redérive que sa propre formule passe en étant faux.

### Reste à faire

- Les **20 captures** ont été régénérées juste après (`tests/captures.py`, hors
  session FreeCAD) et l'import SVG, mode livré en v1.78.0 et documenté nulle
  part, a enfin sa fiche.
- Les mesures d'établi qui débloquent du code : une bande S1000/F800 sur hêtre
  (seule case manquante du tableau), la Planche 2 en multi-feed (sans quoi le
  modèle feed-aware n'a aucun effet mesurable), et une rampe Z pour obtenir
  des largeurs **en défocus** sur hêtre (« ton sur mesure » en dépend).
