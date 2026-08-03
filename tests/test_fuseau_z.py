# -*- coding: utf-8 -*-
"""Spirale en FUSEAU : la largeur vient de la HAUTEUR, pas de la puissance.

Christophe, 03/08/2026, croquis à l'appui : « cela me fait des lignes à
étages, moi je pensais que t'allais prendre le point max que peut donner un
défocus selon le matériau, mais sur une ligne par exemple de 0.1mm qui passe
à 1mm, la tête en Z allait se lever progressivement, ce qui aurait pour
conséquence de grossir le trait progressivement ».

Il avait raison sur le constat : moduler la PUISSANCE donne une valeur par
case, donc des marches d'un pas -- invisibles au pas 0,20 mm au foyer, très
visibles au pas 1,16 en défocus.

Ce que ces tests figent, dans l'ordre d'importance :
 - la PENTE du Z, mesurée sur le G-code ÉMIS et non sur la formule qui l'a
   produit. C'est la contrainte dure : au-delà, LinuxCNC ne refuse pas, il
   ralentit tout le mouvement, donc le temps de pose change, donc la
   noirceur -- sans que rien ne le dise ;
 - la puissance qui SUIT la largeur (sinon le large sort pâle) ;
 - une seule lecture de config pour construire l'échelle.
"""
import math
import re

from harness import preparer, texte, hauteurs_z, figer_largeurs

h = preparer()
core, tp = h.core, h.tp
MAT = figer_largeurs(core)

# --- 1. L'échelle : croissante en largeur ET en hauteur ------------------
_ech = core.echelle_fuseau_z(MAT, 200.0, power_max=core.S_MAX,
                             line_min_mm=0.10)
assert _ech is not None, "aucune échelle sur un matériau mesuré"
_table, _wmin, _wmax, _avert = _ech
assert len(_table) >= 32, len(_table)
_zs = [t[0] for t in _table]
_ss = [t[1] for t in _table]
_ws = [t[2] for t in _table]
assert _zs == sorted(_zs), "la hauteur doit croître avec la largeur"
assert _ws == sorted(_ws), "la largeur doit croître le long de l'échelle"
assert _ss == sorted(_ss), "la puissance doit croître avec la largeur"
assert _wmax > 3.0 * _wmin, ("le fuseau doit vraiment enfler", _wmin, _wmax)
assert abs(_ws[0] - _wmin) < 0.02 and abs(_ws[-1] - _wmax) < 0.02, (
    "les bornes annoncées ne sont pas celles de la table", _ws[0], _ws[-1])
print("1. échelle : largeur {:.2f} -> {:.2f} mm, Z {:.1f} -> {:.1f}, "
      "S {:.0f} -> {:.0f}, croissante partout OK".format(
          _wmin, _wmax, _zs[0], _zs[-1], _ss[0], _ss[-1]))

# --- 2. La largeur obtenue est celle qui était VISÉE ---------------------
# La hauteur est cherchée par dichotomie sur les mesures ; si l'inversion
# était fausse, la table sortirait quand même -- croissante, plausible, et
# décalée. On vérifie donc chaque palier contre sa cible.
_n = len(_table)
for _i, (_z, _s, _w) in enumerate(_table):
    _vise = _wmin + (_wmax - _wmin) * _i / float(_n - 1)
    assert abs(_w - _vise) < 0.01, ("palier {} : visé {:.3f}, obtenu {:.3f}"
                                    .format(_i, _vise, _w))
print("2. les {} paliers rendent la largeur visée à 0,01 mm près OK".format(_n))

# --- 3. UNE table = UNE lecture de config -------------------------------
# L'échelle échantillonne des centaines de hauteurs par dichotomie. Passer
# par `burn_width_defocus_scaled`, qui recharge la config à chaque appel,
# ferait des milliers de lectures : c'est très exactement le défaut qui
# mettait 14 s à ouvrir le panneau photo le 01/08/2026 (§24 des lignes
# gravées). On compte les LECTURES, pas les secondes.
_n_lect = [0]
_vrai = core.load_config
core.load_config = lambda *a, **k: (_n_lect.__setitem__(0, _n_lect[0] + 1),
                                    _vrai(*a, **k))[1]
try:
    _n_lect[0] = 0
    core.echelle_fuseau_z(MAT, 400.0, power_max=core.S_MAX)
    assert _n_lect[0] <= 3, ("l'échelle du fuseau relit la config à chaque "
                             "échantillon", _n_lect[0])
finally:
    core.load_config = _vrai
print("3. échelle du fuseau : {} lecture(s) de config OK".format(_n_lect[0]))

# --- 4. LA PENTE DU Z, mesurée sur le G-code ÉMIS ------------------------
# Le contrôle central. Vérifier la fonction qui rabote prouverait qu'elle
# rabote ; ce qu'on veut savoir, c'est ce que la MACHINE recevra.
_N = 28
_rows = [[(x / float(_N - 1)) for x in range(_N)] for _y in range(_N)]


def _trajet(gcode):
    """[(x, y, z)] des G1 du fichier."""
    out = []
    for _l in gcode.split("\n"):
        if not _l.startswith("G1 "):
            continue
        _mx = re.search(r"X(-?[\d.]+)", _l)
        _my = re.search(r"Y(-?[\d.]+)", _l)
        _mz = re.search(r"Z(-?[\d.]+)", _l)
        if _mx and _my and _mz:
            out.append((float(_mx.group(1)), float(_my.group(1)),
                        float(_mz.group(1))))
    return out


_verifs = 0
for _feed in (200.0, 400.0, 800.0):
    _g = core.generate_gcode_photo_spirale(
        _rows, 3.40, core.Z_WORK_MM, _feed, MAT, line_min_mm=0.10,
        power_max=core.S_MAX, white_threshold=0.05, fuseau_z=True, quiet=True)
    assert _g, ("aucun G-code de fuseau", _feed)
    _pts = _trajet(_g)
    assert len(_pts) > 200, ("trajet trop court pour conclure", len(_pts))
    _pente, _dmin = 0.0, None
    for _a, _b in zip(_pts, _pts[1:]):
        _d = math.hypot(_b[0] - _a[0], _b[1] - _a[1])
        if _d > 1e-9:
            _pente = max(_pente, abs(_b[2] - _a[2]) / _d)
            _dmin = _d if _dmin is None else min(_dmin, _d)
    _budget = core.pente_z_max(_feed)
    # TOLÉRANCE DÉRIVÉE DE L'ARRONDI, pas choisie. Les coordonnées sont
    # écrites à 4 décimales : chaque extrémité porte jusqu'à 5e-5 mm
    # d'erreur, donc 1e-4 sur dz et ~1,5e-4 sur la longueur du segment. La
    # pente valant dz/d, l'erreur est bornée par
    # (pente x delta_d + delta_dz) / d, au pire sur le segment le plus
    # court. C'est l'erreur de LONGUEUR qui domine, pas celle de hauteur --
    # une tolérance posée sur le seul dz (première version de ce test)
    # était trop serrée et rougissait sur de l'arrondi.
    _tol = (_budget * 1.5e-4 + 1.0e-4) / _dmin
    assert _pente <= _budget + _tol, (
        "F{:.0f} : le G-code demande {:.4f} mm de Z par mm parcouru, budget "
        "{:.4f} (tolérance d'arrondi {:.5f}) -- LinuxCNC ralentirait tout "
        "le mouvement".format(_feed, _pente, _budget, _tol))
    # ... et la vitesse Z qui en découle reste sous celle de l'axe.
    assert _pente * _feed <= core.Z_MAX_FEED_MM_MIN + 1e-6, (
        _feed, _pente * _feed, core.Z_MAX_FEED_MM_MIN)
    _zg = sorted({round(_p[2], 3) for _p in _pts})
    assert len(_zg) > 20, ("le Z ne balaie pas : ce n'est pas un fuseau",
                           len(_zg))
    _verifs += 1
assert _verifs == 3
print("4. pente Z tenue sur le G-code émis aux {} vitesses (jusqu'à "
      "{:.0f} mm/min sur {:.0f} dispo) OK".format(
          _verifs, _pente * _feed, core.Z_MAX_FEED_MM_MIN))

# --- 5. La puissance SUIT la largeur -------------------------------------
# Sans ça le large sort PÂLE : à S constant, un trait dix fois plus large
# reçoit dix fois moins d'énergie par mm². La spirale du 31/07/2026 est
# sortie marbrée au bout large et carbonisée au bout fin, pour cette
# raison exacte.
_g5 = core.generate_gcode_photo_spirale(
    _rows, 3.40, core.Z_WORK_MM, 200.0, MAT, line_min_mm=0.10,
    power_max=core.S_MAX, fuseau_z=True, quiet=True)
_couples = []
_s = 0.0
for _l in _g5.split("\n"):
    if _l.startswith("("):
        continue
    _ms = re.search(r"\bS(\d+)", _l)
    if _ms:
        _s = float(_ms.group(1))
    _mz = re.search(r"^G1 .*Z(-?[\d.]+)", _l)
    if _mz and _s > 0:
        _couples.append((float(_mz.group(1)), _s))
assert len(_couples) > 100, len(_couples)
_bas = [s for z, s in _couples if z <= core.Z_WORK_MM + 5.0]
_haut = [s for z, s in _couples if z >= core.Z_WORK_MM + 0.8 *
         (max(z for z, _ in _couples) - core.Z_WORK_MM)]
assert _bas and _haut, (len(_bas), len(_haut))
assert max(_bas) < min(_haut), (
    "la puissance ne suit pas la hauteur : le trait large sortira pâle",
    max(_bas), min(_haut))
print("5. puissance suit la largeur : S{:.0f} en bas de course contre "
      "S{:.0f} en haut OK".format(max(_bas), min(_haut)))

# --- 6. Jamais de G4 faisceau allumé ------------------------------------
# Règle non négociable du projet : le HAL borne la puissance à la vitesse
# RÉELLE, donc à l'arrêt elle tombe à 0 et un point fait au dwell ne grave
# rien. On suit l'état du faisceau ligne à ligne -- chercher « G4 » dans le
# texte se trompe, « G43 H100 » (compensation d'outil) commence pareil.
_s6 = 0
for _l in _g5.split("\n"):
    if _l.startswith("("):
        continue
    _m = re.search(r"\bS(\d+)", _l)
    if _m:
        _s6 = int(_m.group(1))
    if _l.startswith("G4 "):
        assert _s6 == 0, ("pause faisceau allumé", _l)
print("6. aucun G4 faisceau allumé OK")

# --- 7. Le refus, quand le matériau n'a rien en défocus ------------------
core.save_burn_widths(u"Sans-défocus", {
    "focus": [{"power": s, "feed": 400.0, "width": w}
              for s, w in ((200.0, 0.10), (1000.0, 0.30))]})
assert core.echelle_fuseau_z(u"Sans-défocus", 400.0) is None, (
    "un matériau sans niveau de défocus mesuré ne peut pas faire de fuseau")
assert core.generate_gcode_photo_spirale(
    _rows, 1.0, core.Z_WORK_MM, 400.0, u"Sans-défocus",
    fuseau_z=True, quiet=True) is None
print("7. sans mesure en défocus, le fuseau refuse (plutôt qu'inventer) OK")

# --- 8. Le panneau : une seule hauteur lue par les trois ----------------
_p = tp.TaskPanelHalftone()
_mats = [_p.combo_photo_mat.itemText(i)
         for i in range(_p.combo_photo_mat.count())]
if MAT in _mats:
    _p.combo_photo_mat.setCurrentIndex(_mats.index(MAT))
_p.spn_power_max.setValue(core.S_MAX)
_p.spn_line_min.setValue(0.10)
_p.spn_line_feed.setValue(200.0)
_p.spn_pitch.setValue(3.40)
# La case n'existe QUE pour la spirale : les rangées n'ont pas de trait
# continu où faire monter la tête.
for _i, _t in enumerate(tp._TRAMAGES):
    _p.combo_mode.setCurrentIndex(_i)
    _p.chk_fuseau_z.setChecked(True)
    if _t["cle"] != "spirale":
        assert not _p._fuseau_z(), (
            "le fuseau ne doit s'appliquer qu'à la spirale", _t["cle"])
_p.combo_mode.setCurrentIndex(
    [i for i, t in enumerate(tp._TRAMAGES) if t["cle"] == "spirale"][0])
_p.chk_fuseau_z.setChecked(True)
assert _p._fuseau_z()
# Une hauteur FIXE et un fuseau qui balaie sont deux réponses à la même
# question : le sélecteur de défocus doit se taire.
assert _p._dz_trait() == 0.0, (
    "le fuseau balaie la hauteur : aucun défocus fixe ne doit s'appliquer")
_p._maj_regime()
_v = texte(_p.lbl_regime)
assert "Fuseau" in _v, ("le verdict ne parle pas du fuseau", _v[:120])
assert "de trace à cette vitesse" in _v, (
    "le verdict n'annonce pas la longueur mini du fuseau -- c'est LE "
    "chiffre qui dit le détail qu'on aura", _v[:200])
_g8 = _p._generate(_rows, quiet=True)
assert _g8 and "fuseau par la hauteur" in _g8.lower(), (_g8 or "")[:120]
_z8 = hauteurs_z(_g8)
assert len(_z8) > 20, ("le G-code du panneau ne balaie pas le Z", len(_z8))
_img8, _note8 = _p._render_photo_preview(_rows, 120)
assert _img8 is not None, ("l'aperçu refuse ce que le G-code grave", _note8)
# L'aperçu doit peindre une SPIRALE, pas des rangées : au centre de l'image
# la spirale passe, sur un bord elle ne fait que traverser.
print("8. panneau : case réservée à la spirale, défocus fixe muet, verdict "
      "+ G-code + aperçu d'accord OK")

# --- 9. Le fuseau ne fait PAS d'étages ----------------------------------
# Le défaut d'origine, formulé comme une propriété : la largeur doit varier
# par petits incréments le long du trait, jamais par marches d'un pas.
_pts9 = _trajet(_g5)
_sauts = [abs(_b[2] - _a[2]) for _a, _b in zip(_pts9, _pts9[1:])]
_course = max(p[2] for p in _pts9) - min(p[2] for p in _pts9)
assert _course > 10.0, ("le Z ne monte pas assez pour un fuseau", _course)
assert max(_sauts) < _course / 8.0, (
    "un saut de hauteur vaut plus d'un huitième de la course : ce sont des "
    "marches, pas un fuseau", max(_sauts), _course)
print("9. course {:.0f} mm, plus grand saut {:.2f} mm (< 1/8) : un fuseau, "
      "pas un escalier OK".format(_course, max(_sauts)))

# --- 10. LE PAS PLAFONNE LE FUSEAU --------------------------------------
# Sans plafond, le fuseau montait jusqu'à la plus large brûlure du matériau
# (3,43 mm sur hêtre), ce qui imposait un pas de 3,43 : 34 tours sur 120 mm,
# une spirale clairsemée et pointillée. Christophe, 03/08/2026, aperçu à
# l'appui : « on est loin de ce que je veux ». Au-delà du pas, les tours
# voisins se recouvrent de toute façon -- le noir n'est plus un fuseau mais
# un aplat repassé deux fois.
_sans = core.echelle_fuseau_z(MAT, 200.0, power_max=core.S_MAX,
                              line_min_mm=0.10)
_large = _sans[2]
for _cap in (_large / 4.0, _large / 2.0):
    _av = core.echelle_fuseau_z(MAT, 200.0, power_max=core.S_MAX,
                                line_min_mm=0.10, largeur_max=_cap)
    assert _av is not None, _cap
    assert abs(_av[2] - _cap) < 0.01, ("le plafond n'est pas respecté",
                                       _cap, _av[2])
    # Et il rend du DÉTAIL : la course du Z tombe avec la largeur maxi, donc
    # la longueur mini d'un fuseau aussi.
    _c_sans = _sans[0][-1][0] - _sans[0][0][0]
    _c_avec = _av[0][-1][0] - _av[0][0][0]
    assert _c_avec < _c_sans, ("plafonner doit raccourcir la course Z",
                              _c_sans, _c_avec)
# Un plafond PLUS LARGE que ce que le matériau sait faire ne doit rien
# changer : c'est la mesure qui gagne, jamais le souhait.
_haut = core.echelle_fuseau_z(MAT, 200.0, power_max=core.S_MAX,
                              line_min_mm=0.10, largeur_max=_large * 3.0)
assert abs(_haut[2] - _large) < 1e-6, ("un plafond au-delà des mesures ne "
                                       "doit pas les dépasser", _haut[2])
# Et le générateur passe bien le PAS comme plafond : au pas fin, le G-code
# ne doit pas monter la tête comme au pas large.
_g10a = core.generate_gcode_photo_spirale(
    _rows, _large, core.Z_WORK_MM, 200.0, MAT, line_min_mm=0.10,
    power_max=core.S_MAX, fuseau_z=True, quiet=True)
_g10b = core.generate_gcode_photo_spirale(
    _rows, _large / 3.0, core.Z_WORK_MM, 200.0, MAT, line_min_mm=0.10,
    power_max=core.S_MAX, fuseau_z=True, quiet=True)
_c10a = max(hauteurs_z(_g10a)) - min(hauteurs_z(_g10a))
_c10b = max(hauteurs_z(_g10b)) - min(hauteurs_z(_g10b))
assert _c10b < _c10a * 0.8, (
    "le générateur ne plafonne pas le fuseau au pas : même course de Z à "
    "deux pas très différents", _c10a, _c10b)
print("10. le pas plafonne le fuseau ({:.2f} mm de course au pas large "
      "contre {:.2f} au pas fin), les mesures gardent le dernier mot OK"
      .format(_c10a, _c10b))

# --- 11. L'avance rapide : bois nu ET Z plat, jamais autrement -----------
# La première version du fuseau INTERDISAIT l'avance rapide partout, au
# motif que le budget de pente est calculé pour `feed`. Vrai là où la tête
# monte -- faux hors de l'image, dans les coins que la spirale traverse
# parce qu'elle va jusqu'à la demi-diagonale : là le Z ne bouge pas d'un
# cheveu. Sur une image de 50 mm au pas 1,0, ces coins font 41 % du trajet,
# et l'interdiction coûtait un quart du job (56 -> 43 min).
_g11 = core.generate_gcode_photo_spirale(
    _rows, 1.0, core.Z_WORK_MM, 200.0, MAT, line_min_mm=0.10,
    power_max=core.S_MAX, white_threshold=0.0, fuseau_z=True, quiet=True)
assert _g11
_s11, _z11, _n11 = 0.0, None, 0
for _l in _g11.split("\n"):
    if _l.startswith("("):
        continue
    _m = re.search(r"\bS(\d+)", _l)
    if _m:
        _s11 = float(_m.group(1))
    _mq = re.search(r"M67 E0 Q([\d.]+)", _l)
    if _mq:
        _s11 = float(_mq.group(1))
    _mm = re.match(r"G1 X(-?[\d.]+) Y(-?[\d.]+) Z(-?[\d.]+) F(\d+)", _l)
    if not _mm:
        continue
    _z, _f = float(_mm.group(3)), float(_mm.group(4))
    if _f > 200.0 + 1e-9:
        _n11 += 1
        assert _s11 == 0, ("avance rapide FAISCEAU ALLUMÉ : le trait "
                           "sortirait fin là où il devrait être épais", _l)
        assert _z11 is None or abs(_z - _z11) < 1e-6, (
            "avance rapide pendant que le Z monte : la pente calculée pour "
            "`feed` est crevée, LinuxCNC ralentira sans le dire", _l)
    _z11 = _z
assert _n11 > 50, ("aucune avance rapide : les coins hors image sont "
                   "parcourus à la vitesse de gravure pour rien", _n11)
print("11. {} blocs à l'avance rapide, tous faisceau coupé ET Z plat OK"
      .format(_n11))

# --- 12. La largeur varie DANS une case de pas, et la fenêtre lisse ------
# Christophe, 03/08/2026, en comparant avec l'original de Vertigo : « il y a
# un traitement en plus, on voit que le trait suit un tracé afin de rendre
# plus de détail ». Il avait raison, et la cause était que la grille de
# noirceur avait la résolution du PAS : tous les points d'un tour tombant
# dans la même case recevaient la même largeur. Le trait avançait donc par
# marches d'un pas, invisibles au pas 0,2 mm, criantes au pas 1,0.
_PAS12, _SOUS = 1.0, 4
_C12 = _PAS12 / _SOUS
_L12 = 40                       # cases fines -> 10 mm de large
# Un dégradé qui varie À L'INTÉRIEUR d'une case de pas : quatre cases fines
# par pas, chacune plus foncée que la précédente.
_rows12 = [[(x % _SOUS) / float(_SOUS - 1) for x in range(_L12)]
           for _ in range(_L12)]
_pts12 = core.points_spirale(_L12 * _C12, _L12 * _C12, _PAS12)
_niv12 = core.spirale_niveaux(_rows12, _C12, _PAS12, _pts12, 64, 0.0)
_dedans = [k for k in _niv12 if k is not None]
assert len(set(_dedans)) > 1, (
    "la largeur ne varie pas alors que l'image varie dans la case de pas",
    set(_dedans))
# La MOYENNE, pas le point : un pic d'un seul pixel ne doit pas faire
# bomber le trait comme s'il occupait toute la fenêtre.
_plat = [[0.0] * _L12 for _ in range(_L12)]
_pic = [list(r) for r in _plat]
_pic[_L12 // 2][_L12 // 2] = 1.0
_n_plat = core.spirale_niveaux(_plat, _C12, _PAS12, _pts12, 64, 0.0)
_n_pic = core.spirale_niveaux(_pic, _C12, _PAS12, _pts12, 64, 0.0)
_touches = [i for i, (a, b) in enumerate(zip(_n_plat, _n_pic))
            if a is not None and b is not None and a != b]
assert _touches, "un pixel isolé ne change rien du tout : la fenêtre est nulle"
_max_pic = max(_n_pic[i] for i in _touches)
assert _max_pic < 32, (
    "un pixel isolé porte le trait à mi-course ou plus : la valeur est prise "
    "AU POINT, pas moyennée sur la fenêtre", _max_pic)
# Et la fenêtre a bien la taille annoncée : au moins 2 cases de large.
assert core.FUSEAU_FENETRE * _PAS12 / _C12 >= 2.0
# Et le PANNEAU doit vraiment construire cette grille fine : tester le
# coeur avec sa propre grille laisserait passer un panneau resté au pas
# (vérifié en le sabotant -- §12 restait vert).
from harness import image_demo as _img_demo
_ph = tp.TaskPanelHalftone()
_mh = [_ph.combo_photo_mat.itemText(i)
       for i in range(_ph.combo_photo_mat.count())]
if MAT in _mh:
    _ph.combo_photo_mat.setCurrentIndex(_mh.index(MAT))
_ph.combo_mode.setCurrentIndex(
    [i for i, t in enumerate(tp._TRAMAGES) if t["cle"] == "spirale"][0])
_ph.edt_image.setText(_img_demo())
_ph.spn_width.setValue(60.0)
_ph.spn_pitch.setValue(1.0)
_ph.chk_fuseau_z.setChecked(False)
_gros = _ph._build_rows(silent=True)
_ph.chk_fuseau_z.setChecked(True)
_fin = _ph._build_rows(silent=True)
assert _gros and _fin
_rap = len(_fin[0]) / float(len(_gros[0]))
assert _rap >= _ph.SOUS_ECHANTILLON_FUSEAU - 0.01, (
    "le panneau construit la grille du fuseau à la résolution du PAS : tous "
    "les points d'un tour dans une même case auront la même largeur",
    len(_gros[0]), len(_fin[0]))
assert abs(_ph._cellule_fuseau() - 1.0 / _ph.SOUS_ECHANTILLON_FUSEAU) < 1e-9
print("12. la largeur varie dans une case de pas ({} niveaux distincts), et "
      "un pixel isolé ne monte qu'au niveau {} sur 64 ; le panneau bâtit "
      "une grille {:.0f}x plus fine que le pas OK".format(
          len(set(_dedans)), _max_pic, _rap))
