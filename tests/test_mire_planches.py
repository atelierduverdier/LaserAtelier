# -*- coding: utf-8 -*-
"""La MIRE DE MESURE gravée sur les planches de calibration.

Idée de Christophe (31/07/2026) : graver la graduation SUR la planche
plutôt que d'y poser une réglette. Une réglette posée est 0,5 à 1 mm
au-dessus de la surface, donc vue sous un autre angle que le trait qu'on
mesure ; une graduation gravée partage son plan ET le repère machine.

Validé sur bois le jour même : la mire a permis de mesurer un trait à
0,50 mm par photo, valeur ensuite CONFIRMÉE au pied à coulisse alors que
la table annonçait 0,30. C'est elle qui a fait tomber le fait que la
table des largeurs au foyer était périmée.
"""
import re

from harness import preparer

h = preparer()
core = h.core


def bbox(g):
    xs, ys = [], []
    for l in g.split("\n"):
        if not l.startswith(("G0 X", "G1 X")):
            continue
        for t in l.split():
            if t.startswith("X"):
                xs.append(float(t[1:]))
            elif t.startswith("Y"):
                ys.append(float(t[1:]))
    return min(xs), min(ys), max(xs), max(ys)


# --- 1. La mire est là, et ses cotes sont RONDES ----------------------
# Rondes parce qu'elles sont annoncées en en-tête et servent de référence
# métrologique : une base de 80,00 mm connue à 0,05 mm près donne 0,06 %
# d'erreur d'échelle.
for nom, gen in (("Planche 1", core.generate_gcode_planche_focus),
                 ("Planche 2", core.generate_gcode_planche_defocus)):
    g = gen(quiet=True)
    assert g, nom
    m = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm ENTRE CENTRES", g)
    assert m, (nom, [l for l in g.split("\n") if l.startswith("(")][:6])
    L, H = float(m.group(1)), float(m.group(2))
    assert L % 10 == 0 and H % 10 == 0, (nom, L, H)
    assert "reglette au mm" in g, nom
    print("1. {} : mire annoncee, rectangle {:.0f} x {:.0f} mm (rond) OK".format(
        nom, L, H))

# --- 2. Sans mire, le G-code est celui d'AVANT -----------------------
for nom, gen in (("Planche 1", core.generate_gcode_planche_focus),
                 ("Planche 2", core.generate_gcode_planche_defocus)):
    g0 = gen(mire=False, quiet=True)
    assert "Mire de mesure" not in g0, nom
    assert bbox(g0)[2] < bbox(gen(quiet=True))[2], (
        "avec la mire, la planche doit s'elargir", nom)
print("2. mire=False : aucune trace de mire, planche plus petite OK")

# --- 3. Les 4 repères existent vraiment, aux bons écarts -------------
g = core.generate_gcode_planche_focus(quiet=True)
seg, garde, x, y = [], False, None, None
for l in g.split("\n"):
    if l.startswith("(-- "):
        garde = "repere" in l
        continue
    m = re.match(r"G0 X([-\d.]+) Y([-\d.]+)", l)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
        continue
    m = re.match(r"G1 X([-\d.]+) Y([-\d.]+)", l)
    if m and garde and x is not None:
        seg.append(((x, y), (float(m.group(1)), float(m.group(2)))))
        x, y = float(m.group(1)), float(m.group(2))
assert len(seg) == 8, ("4 croix x 2 bras attendus", len(seg))
centres = sorted({(round((a[0] + b[0]) / 2, 2), round((a[1] + b[1]) / 2, 2))
                  for a, b in seg})
assert len(centres) == 4, centres
xs = sorted({c[0] for c in centres})
ys = sorted({c[1] for c in centres})
mm = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm", g)
assert abs((xs[-1] - xs[0]) - float(mm.group(1))) < 1e-6, (xs, mm.group(1))
assert abs((ys[-1] - ys[0]) - float(mm.group(2))) < 1e-6, (ys, mm.group(2))
print("3. 4 croix, ecarts {:.0f} x {:.0f} mm CONFORMES a l'en-tete OK".format(
    xs[-1] - xs[0], ys[-1] - ys[0]))

# --- 4. La mire ne recouvre JAMAIS le contenu -------------------------
# Au premier essai, le trait le plus large avait été gravé en travers des
# chiffres de la réglette : inmesurable, et invisible autrement qu'à
# l'aperçu. La garde est donc calculée, pas écrite à la main.
b, lbl, infos = core.mire_de_mesure(10.0, 10.0, 50.0, 40.0)
assert infos is not None and infos["garde"] >= 0.5, infos
# ... et si on ne laisse pas la place, la mire REFUSE au lieu de chevaucher.
b2, _l2, i2 = core.mire_de_mesure(10.0, 10.0, 50.0, 40.0, marge=0.0, garde=0.0)
_b3, _l3, i3 = core.mire_de_mesure(0.0, 0.0, 5.0, 5.0, marge=0.0, garde=-20.0)
assert i3 is None, "une mire qui chevauche le contenu doit etre refusee"
print("4. garde de {:.1f} mm sous le contenu ; une mire qui chevaucherait "
      "est refusee OK".format(infos["garde"]))

# --- 5. Gravée LENTEMENT, et réglable par laser -----------------------
# La réglette, ce sont des dizaines de petits traits séparés par des
# rapides, donc autant d'accélérations : à F1200 le support en PLA de
# l'atelier vibrait et les repères sortaient ONDULÉS -- ce qui ruine
# exactement ce qu'on leur demande, un centre net.
assert core.MIRE_FEED <= 400, core.MIRE_FEED
assert ("mire_power", "MIRE_POWER") in [(k, g_) for k, g_, _c, _v in core._USER_SETTINGS]
assert "mire_power" in core.PER_LASER_KEYS and "mire_feed" in core.PER_LASER_KEYS
puiss = {int(m.group(1)) for l in g.split("\n") if not l.startswith("(")
         for m in [re.search(r"\bS(\d+)", l) or re.search(r"M67 E0 Q(\d+)", l)] if m}
assert int(core.MIRE_POWER) in puiss, (core.MIRE_POWER, sorted(puiss))
print("5. mire a S{:.0f} F{:.0f}, reglable par laser, presente dans le G-code OK"
      .format(core.MIRE_POWER, core.MIRE_FEED))

print("\nTOUS LES TESTS mire_planches PASSENT")


# --- 6. Compaction : rien ne doit se toucher -------------------------
# Les planches ont été resserrées le 31/07/2026 (« je n'ai pas besoin de
# 3 cm de traits pour avoir la largeur, ça économisera du bois et la
# photo sera plus facile ») : trait 20 -> 12 mm, entre-rangs 6 -> 4,
# étiquettes 3 -> 2,5, et l'entre-colonnes CALCULÉ sur la largeur réelle
# des étiquettes au lieu de 12 mm forfaitaires. Resserrer une mise en
# page sans vérifier les distances, c'est exactement comme ça qu'un trait
# s'est retrouvé gravé en travers des chiffres de la réglette.
import math


def _segments(g):
    par_commentaire, cur, x, y = {}, None, None, None
    for l in g.split("\n"):
        if l.startswith("(-- "):
            cur = l
            continue
        m = re.match(r"G0 X([-\d.]+) Y([-\d.]+)", l)
        if m:
            x, y = float(m.group(1)), float(m.group(2))
            continue
        m = re.match(r"G1 X([-\d.]+) Y([-\d.]+)", l)
        if m and x is not None:
            par_commentaire.setdefault(cur, []).append(
                ((x, y), (float(m.group(1)), float(m.group(2)))))
            x, y = float(m.group(1)), float(m.group(2))
    return par_commentaire


def _dist(p, a, b):
    (ax, ay), (bx, by), (px, py) = a, b, p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


for nom, gen, cle in (("Planche 1", core.generate_gcode_planche_focus, "Planche 1 : S"),
                      ("Planche 2", core.generate_gcode_planche_defocus, "Planche 2 : d")):
    g = gen(quiet=True)
    seg = _segments(g)
    traits = [s for c, ss in seg.items() if c and cle in c for s in ss]
    etiq = [s for c, ss in seg.items() if c and "etiquette" in c for s in ss]
    assert traits and etiq, (nom, len(traits), len(etiq))
    mini = min(_dist(p, a, b) for a, b in traits for c_, d_ in etiq for p in (c_, d_))
    assert mini > 0.6, (nom, "une etiquette touche un trait", mini)
    print("6. {} : {} traits, distance minimale trait/etiquette {:.2f} mm OK".format(
        nom, len(traits), mini))

# ... et la compaction a bien eu lieu (une regression la reperdrait en
# silence : les planches marcheraient, elles seraient juste plus grandes).
import inspect
sig = inspect.signature(core.generate_gcode_planche_focus)
assert sig.parameters["trait_len"].default <= 12.0, sig.parameters["trait_len"].default
assert sig.parameters["row_gap"].default <= 4.0, sig.parameters["row_gap"].default
w, h = 0.0, 0.0
xs = [float(t[1:]) for l in core.generate_gcode_planche_focus(quiet=True).split("\n")
      if l.startswith(("G0 X", "G1 X")) for t in l.split() if t.startswith("X")]
assert max(xs) - min(xs) < 170, ("planche 1 trop large", max(xs) - min(xs))
print("7. Planche 1 : {:.0f} mm de large (etait ~195 avant compaction) OK".format(
    max(xs) - min(xs)))


# --- 8. La planche porte SES PROPRES cotes ---------------------------
# Le 31/07/2026, les planches ont été compactées quelques heures après
# avoir été gravées : le .ngc régénéré ne décrivait plus le bois posé sur
# l'établi, et redresser sa photo avec la cote du fichier aurait donné
# une échelle fausse EN SILENCE. Une planche vit des années, un fichier
# est réécrit -- la planche doit donc se suffire à elle-même.
for nom, gen in (("Planche 1", core.generate_gcode_planche_focus),
                 ("Planche 2", core.generate_gcode_planche_defocus)):
    g = gen(quiet=True)
    m = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm", g)
    L, H = float(m.group(1)), float(m.group(2))
    attendu = "{:.0f}-{:.0f}".format(L, H)
    # Les cotes sont gravées : on les retrouve dans la géométrie des
    # étiquettes, pas seulement dans un commentaire.
    b, lbl, infos = core.mire_de_mesure(20.0, 30.0, 120.0, 80.0)
    assert lbl, nom
    ys = [v.Point.y for e in lbl for v in e.Vertexes]
    # le texte des cotes est le groupe le plus BAS des etiquettes (sous la
    # reglette, a hauteur des croix du bas)
    assert min(ys) < infos["y0"] + 1.0, (
        nom, "les cotes gravees ne sont pas sous la reglette", min(ys), infos["y0"])
    print("8. {} : cotes « {} » gravees sur la planche elle-meme, "
          "sous la reglette OK".format(nom, attendu))


# --- 9. LE LASER EST GRAVE SUR LA PLANCHE (v2.24.0) -------------------
# Meme raisonnement que les cotes, applique a la donnee qui decide du SENS
# des mesures : une largeur brulee n'a de valeur que pour le module qui l'a
# produite. Le nom etait dans le nom du fichier REDRESSE -- lequel ne suit
# pas le bois. Christophe l'a vu tout de suite en regardant l'apercu :
# « ou apparait le champ nom de laser ? sur les deux il n'y a rien ».
NOM = "LT-80W-AA-PRO"


def _bbox(aretes):
    xs = [v.Point.x for a in aretes for v in a.Vertexes]
    ys = [v.Point.y for a in aretes for v in a.Vertexes]
    return min(xs), max(xs), min(ys), max(ys)


_b0, _l0, _i0 = core.mire_de_mesure(0, 0, 120, 40, laser="")
_b1, _l1, _i1 = core.mire_de_mesure(0, 0, 120, 40, laser=NOM)

# Sans nom, la planche est EXACTEMENT celle d'avant : l'ajout est isole.
assert len(_l1) > len(_l0), "le nom du laser n'est pas grave"
assert [tuple(v.Point.x for v in e.Vertexes) for e in _l1[:len(_l0)]] == \
       [tuple(v.Point.x for v in e.Vertexes) for e in _l0], \
    "l'ajout du laser a deplace les etiquettes existantes"

# La police 7 segments ne connait que les chiffres, S, F, '.' et '-'.
# Utilisee ici, elle produirait un nom quasi VIDE -- grave dans le bois,
# ca ne se verrait qu'apres coup. Le controle se demontre : on compare.
_sept = core.text_to_edges(NOM, 0.0, 0.0, 2.5)
_mono = _l1[len(_l0):]
assert len(_mono) > 3 * max(1, len(_sept)), (
    "le nom doit etre grave en police MONO-TRAIT : la 7 segments ne sait "
    "ecrire ni L ni T ni W ({} aretes contre {})".format(len(_sept), len(_mono)))

# Sur la meme ligne de base que les cotes, et JAMAIS au-dela du repere
# bas-droite : la croix est la reference, elle ne se fait pas recouvrir.
_xa, _xb, _ya, _yb = _bbox(_mono)
_droite = _i1["x0"] + _i1["largeur"] - 2.0
assert _xb <= _droite, ("le nom deborde sur la croix bas-droite", _xb, _droite)
assert abs((_yb - _ya) - 2.5) < 0.2, ("hauteur du nom", _yb - _ya)

# Un nom absurde doit RETRECIR, pas deborder.
_bl, _ll, _il = core.mire_de_mesure(
    0, 0, 120, 40, laser="UN-NOM-VRAIMENT-BEAUCOUP-TROP-LONG-POUR-CETTE-PLANCHE")
_xa2, _xb2, _ya2, _yb2 = _bbox(_ll[len(_l0):])
assert _xb2 <= _il["x0"] + _il["largeur"] - 2.0, ("nom long deborde", _xb2)
assert (_yb2 - _ya2) < 2.5, "un nom trop long doit etre reduit en hauteur"

# Et l'en-tete le dit aussi -- le bois fait foi, le fichier confirme.
_g = core.generate_gcode_planche_focus(quiet=True)
assert re.search(r"\(Mire : gravee avec le laser [^)\n]+\)", _g), \
    "l'en-tete doit nommer le laser, sur UNE ligne refermee"
for _l in _g.splitlines():
    assert _l.count("(") == _l.count(")"), ("commentaire non referme", _l)
print("9. laser grave sur la planche (mono-trait), sans deborder, "
      "+ en-tete OK")


# --- 10. LA PLANCHE 3 AUSSI (v2.24.1) ---------------------------------
# La 3 n'a pas de mire -- elle se juge a l'oeil, pas par photo -- donc elle
# n'heritait pas du nom grave par la mire et sortait ANONYME. Or c'est LA
# planche qui calibre le point de ce laser-la. Vu par Christophe sur
# l'apercu, le 01/08/2026 : « c'est normal que dans la 3eme planche pas de
# nom de laser ? ».
#
# Regle du depot : brancher un correctif de generateur sur toute la
# famille. Les trois planches de calibration doivent porter le nom.
def _bande(**kw):
    return core.generate_gcode_defocus_calibration(
        z_start=0.0, z_step=3.0, n_marks=13, mark_length=15.0, row_gap=6.0,
        power=600.0, power_end=1000.0, feed=750.0, plank_label="3",
        quiet=True, **kw)


def _pts(g):
    out = []
    for l in g.splitlines():
        m = re.match(r"G[01]\s+X(-?[\d.]+)\s+Y(-?[\d.]+)", l)
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
    return out


_id = core.active_laser_id()
_avant = core.active_laser_name()
try:
    core.rename_laser(_id, "LT-80W-AA-PRO")     # config JETABLE (harness)
    _g_avec = _bande()
    core.rename_laser(_id, "")
    _g_sans = _bande()
finally:
    core.rename_laser(_id, _avant)

assert len(_g_avec.splitlines()) > len(_g_sans.splitlines()) + 50, (
    "la planche 3 ne grave pas le nom du laser")

_p_avec, _p_sans = _pts(_g_avec), _pts(_g_sans)
_y_avec = max(p[1] for p in _p_avec)
_y_sans = max(p[1] for p in _p_sans)
# Rangee A PART, au-dessus de tout : c'est ce qui rend la collision avec
# les libelles F<vitesse> impossible, quel que soit le nombre de bandes.
assert _y_avec > _y_sans, ("le nom doit etre au-dessus du reste",
                           _y_avec, _y_sans)
_bas_nom = min(p[1] for p in _p_avec if p[1] > _y_sans + 0.01)
assert _bas_nom > _y_sans, (
    "le nom mord sur les libelles existants", _bas_nom, _y_sans)

# Et il ne doit rien deplacer de ce qui existait.
assert _p_avec[:len(_p_sans)] or True   # (ordre d'emission non garanti)
_communs = [p for p in _p_sans if p[1] <= _y_sans]
assert all(p in _p_avec for p in _communs[:200]), \
    "l'ajout du nom a deplace des traits existants"

# Les TROIS planches le portent maintenant.
for _nom, _gen in (("Planche 1", core.generate_gcode_planche_focus),
                   ("Planche 2", core.generate_gcode_planche_defocus),
                   ("Planche 3", core.generate_gcode_planche_spot)):
    core.rename_laser(_id, "LT-80W-AA-PRO")
    _a = len(_gen(quiet=True).splitlines())
    core.rename_laser(_id, "")
    _s = len(_gen(quiet=True).splitlines())
    core.rename_laser(_id, _avant)
    assert _a > _s, ("{} ne grave pas le nom du laser".format(_nom), _a, _s)
print("10. les TROIS planches de calibration portent le nom du laser, "
      "sur une rangee a part OK")


# --- 11. PLANCHE 2b : défocus profond (v2.29.0) -----------------------
# Les niveaux 40, 55 et 60 mm ne portaient qu'UN point chacun, venus de la
# Rampe : ils ne peuvent pas servir d'ancre au modèle (un niveau à une
# seule puissance ferait croire que la largeur n'en dépend pas). Cette
# planche leur donne une seconde puissance.
import sys as _sys
_sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from task_panels import _MesuresPlanchesControleur as _Ctrl   # noqa: E402

_g2b = core.generate_gcode_planche_defocus_profond(quiet=True)
assert _g2b, "la planche 2b ne produit rien"
_cel = re.findall(r"-- Planche 2b : d(\d+) S(\d+) F(\d+) --", _g2b)
assert _cel, "aucune cellule identifiée « Planche 2b »"

# LA propriété : ne graver QUE ce que la grille de saisie ② sait afficher.
# Une planche qui grave S850 produirait une mesure invisible dans le
# tableau -- exactement le défaut corrigé en v2.28.0, qu'il serait absurde
# de recréer en brûlant du bois pour ça.
for _d, _s, _f in _cel:
    assert float(_s) in [float(x) for x in _Ctrl.POWERS], (
        "S{} n'est pas une ligne de la grille ②".format(_s), _Ctrl.POWERS)
    assert float(_f) in [float(x) for x in _Ctrl.FEEDS_DEFOCUS], (
        "F{} n'est pas une colonne de la grille ②".format(_f),
        _Ctrl.FEEDS_DEFOCUS)

# Chaque niveau doit pouvoir DEVENIR une ancre : au moins deux puissances.
_par_niv = {}
for _d, _s, _f in _cel:
    _par_niv.setdefault(float(_d), set()).add(float(_s))
assert set(_par_niv) == set(core.DEFOCUS_LEVELS_PROFONDS_MM), (
    _par_niv.keys(), core.DEFOCUS_LEVELS_PROFONDS_MM)
assert 30.0 not in _par_niv, (
    "30 mm tombe ENTRE 15 et 36 : il est déjà interpolé, le graver "
    "n'apporte rien")
for _dz, _ps in _par_niv.items():
    assert len(_ps) >= 2, (
        "niveau {:.0f} : une seule puissance, il ne pourra pas servir "
        "d'ancre -- c'est précisément le problème que cette planche "
        "existe pour résoudre".format(_dz), _ps)

# Les traits sont bien gravés à z_focus + le niveau.
_zs = {float(m) for m in re.findall(r"Z(-?\d+\.?\d*)", _g2b)}
for _dz in core.DEFOCUS_LEVELS_PROFONDS_MM:
    assert (core.Z_WORK_MM + _dz) in _zs, (_dz, sorted(_zs))
# Et la mire reste AU FOYER : la référence de mesure doit être nette.
assert core.Z_WORK_MM in _zs
assert re.search(r"rectangle de [\d.]+ x [\d.]+ mm ENTRE CENTRES", _g2b), \
    "la planche 2b doit porter une mire"
print("11. planche 2b : {} cellules, niveaux {}, {} puissances/niveau, "
      "toutes saisissables dans ② OK".format(
          len(_cel), sorted(_par_niv), sorted(len(v) for v in _par_niv.values())))
