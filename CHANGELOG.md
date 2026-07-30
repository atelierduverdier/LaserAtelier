# Journal des versions

Ce journal commence à la **v2.0.0**. Pour tout ce qui précède, `git log
--oneline` est la source de vérité — chaque message de commit y raconte le
pourquoi, souvent avec les chiffres mesurés qui l'ont motivé.

Les versions suivent `MAJEURE.MINEURE.CORRECTIF`. `VERSION` dans
`laser_core.py` est la source unique ; elle est bumpée en même temps que
`package.xml`, le badge de `docs/index.html`, le `README` et `docs/manuel.html`
(+ régénération du PDF), dans un seul commit.

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

- Les **19 captures d'écran** du manuel datent du 24 au 28 juillet.
  `halftone.png` précède les trois tramages ajoutés depuis, et l'import SVG
  n'a jamais eu la sienne. À régénérer via la session FreeCAD (grab avec
  `WA_DontShowOnScreen` + autocrop).
- Les mesures d'établi qui débloquent du code : une bande S1000/F800 sur hêtre
  (seule case manquante du tableau), la Planche 2 en multi-feed (sans quoi le
  modèle feed-aware n'a aucun effet mesurable), et une rampe Z pour obtenir
  des largeurs **en défocus** sur hêtre (« ton sur mesure » en dépend).
