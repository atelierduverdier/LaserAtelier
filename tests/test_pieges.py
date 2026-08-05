# -*- coding: utf-8 -*-
"""Les pièges que ce dépôt a DÉJÀ payés, balayés sur tout le code.

Christophe, 05/08/2026 : « on arrive bientôt à la v3, j'aimerais bien
maintenant corriger des bugs pour avoir une v3 stable comme les pros ».

La meilleure piste n'est pas de chercher au hasard. Chaque règle de
`.claude/rules/` raconte un défaut qui a coûté une planche, une heure ou un
document -- et plusieurs annoncent « corrigé sur les N sites ». Or le 5 août
un neuvième site de `hasattr(ViewObject)` dormait dans les hachures, et deux
autres dans la planche d'ajustement, alors que la règle disait huit. UN
BALAYAGE FAIT UNE FOIS N'EST PAS UNE PROPRIÉTÉ : il faut le rejouer à chaque
exécution, sinon le piège revient par la porte de derrière.

Ce fichier ne teste donc pas un comportement mais une ABSENCE, sur
l'ensemble des sources. Toute nouvelle famille de défaut trouvée à
l'établi a vocation à venir ici.
"""
import os
import re

from harness import preparer

h = preparer()
core = h.core
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ("laser_core.py", "task_panels.py", "commands.py", "InitGui.py",
           "svg_import.py", "laser_jobs.py", "calligraphie.py")


def _lire(nom):
    with open(os.path.join(RACINE, nom), encoding="utf-8") as f:
        return f.read()


# --- 1. hasattr SUR ViewObject : VRAI ET INUTILE EN HEADLESS -------------
# L'attribut EXISTE et vaut None hors interface, donc la ligne suivante meurt
# sur `None.LineColor`. La règle des panneaux annonçait « corrigé aux 8
# sites » ; il en restait trois le 05/08/2026 (hachures, découpe et gravure
# de la planche d'ajustement). C'est ce mensonge-là que ce contrôle empêche.
_coupables = []
for _nom in SOURCES:
    for _n, _l in enumerate(_lire(_nom).splitlines(), 1):
        if re.search(r"hasattr\([^,]+,\s*['\"]ViewObject['\"]\)", _l):
            _coupables.append("{}:{}".format(_nom, _n))
assert not _coupables, (
    "hasattr sur ViewObject : VRAI et INUTILE en headless -- l'attribut "
    "existe et vaut None, et la ligne suivante meurt dessus. Utiliser "
    "getattr(obj, 'ViewObject', None) is not None", _coupables)
print("1. aucun hasattr sur ViewObject dans les {} sources OK".format(
    len(SOURCES)))


# --- 2. AUCUN G4 AVEC LE FAISCEAU ALLUMÉ (non-négociable n°4) -----------
# Le HAL ramène la puissance à zéro à l'arrêt : un point fait au dwell ne
# grave RIEN et le job sort blanc, sans un mot. Tout point est un
# micro-trait. Seul l'armement -- faisceau à zéro -- a le droit au dwell.
# ON NE VISE QUE LES ÉMISSIONS. `estimate_job_time_seconds` LIT les G4 pour
# compter le temps d'attente : un balayage qui l'attrape crie au loup et
# finit par être désarmé, ce qui est pire que pas de contrôle du tout.
_LECTURE = ("startswith", "endswith", "==", "in line", "split", "strip")
_g4 = []
for _nom in SOURCES:
    for _n, _l in enumerate(_lire(_nom).splitlines(), 1):
        if not re.search(r"""["']G4\b""", _l):
            continue
        if any(_m in _l for _m in _LECTURE):
            continue                       # on lit du G-code, on n'en écrit pas
        if "ARM" in _l or "dwell=" in _l:
            continue                       # l'armement, faisceau à zéro
        _g4.append("{}:{}  {}".format(_nom, _n, _l.strip()[:60]))
assert not _g4, (
    "un G4 est émis hors de l'armement : si le faisceau est allumé, il ne "
    "grave RIEN et le job sort blanc sans un mot", _g4)
print("2. aucun G4 hors armement OK")


# --- 3. TOUT GÉNÉRATEUR ASSAINIT SA SORTIE -----------------------------
# Un commentaire NON FERMÉ fait refuser le programme entier au chargement
# (« Unclosed comment found ») : le job ne démarre jamais. Le sanitizer est
# le filet, et il doit être au bout de CHAQUE générateur -- en oublier un ne
# se voit qu'à la machine, devant une planche montée.
_src_core = _lire("laser_core.py")
_gens = re.findall(r"^def (generate_gcode_\w+)\(", _src_core, re.M)
assert len(_gens) >= 20, ("trop peu de générateurs trouvés : le balayage "
                          "vise à côté", len(_gens))
_sans_filet = []
for _g in _gens:
    _i = _src_core.index("def {}(".format(_g))
    _j = _src_core.find("\ndef ", _i + 5)
    _corps = _src_core[_i:_j if _j > 0 else len(_src_core)]
    _rendus = [_r for _r in re.findall(r"return ([^\n]+)", _corps)
               if '"\\n".join' in _r or ("lines" in _r and "join" in _r)]
    for _r in _rendus:
        if "sanitize_gcode_for_linuxcnc" not in _r:
            _sans_filet.append("{} -> {}".format(_g, _r.strip()[:60]))
assert not _sans_filet, (
    "un générateur rend son G-code SANS l'assainir : un commentaire non "
    "fermé ou un accent feront refuser le programme au chargement",
    _sans_filet)
print("3. les {} générateurs assainissent leur sortie OK".format(len(_gens)))


# --- 4. LE CONTRÔLE DES COULEURS EN DUR : ÉCRIT, MESURÉ, PUIS JETÉ -----
# Il devait interdire toute couleur posée en dur, après le vert des hachures
# qui se confondait avec celui du marquage. Deux mesures l'ont condamné :
#
#   * il attrape DIX couleurs parfaitement légitimes -- le magenta des
#     marqueurs de collision, le brun d'encre des textes posés, des gris de
#     repère -- dont aucune ne participe au langage des calques ;
#   * et il N'AURAIT PAS ATTRAPÉ LE VRAI CAS : l'ancien vert (0.0, 0.8, 0.0)
#     est à 0,85 du vert du marquage en distance RVB, plus loin que tout
#     seuil qu'on aurait osé poser. La collision était PERCEPTUELLE, pas
#     numérique.
#
# Un chiffre qui ne sépare pas ce qu'il prétend séparer rassure à tort et
# finit par être désarmé -- la leçon du détecteur de fût contourné (27 %
# contre 28 %). On préfère ne rien mettre, et le dire.
print("4. (contrôle des couleurs en dur écarté : mesuré incapable de "
      "séparer -- cf. le commentaire)")


# --- 5. UN ENREGISTREMENT NE DOIT PAS SUPPRIMER CE QU'IL NE SAIT PAS LIRE
# `save_shades` REMPLACE la liste du matériau : tout ce que le panneau ne
# rend pas est effacé. Or le Nuancier jetait une ligne dont un nombre était
# illisible -- une cellule blanchie par mégarde sur un ton MESURÉ AU PIED À
# COULISSE -- avec un simple avertissement console. Et le message de succès
# annonçait `rowCount()`, donc il pouvait se féliciter d'un enregistrement
# complet juste après en avoir perdu trois.
#
# C'est la règle de la v2.4.0 (« ② ne doit jamais effacer ce qu'il ne sait
# pas AFFICHER ») appliquée à ce qu'il ne sait pas LIRE.
from harness import sans_dialogues                             # noqa: E402
import task_panels as tp                                       # noqa: E402

sans_dialogues()
_p5 = tp.TaskPanelNuancier()
_p5.combo_mat.setEditText("EssaiPieges")
_p5.table.setRowCount(0)


def _poser(r, valeurs):
    _p5.table.insertRow(r)
    for _c, _v in enumerate(valeurs):
        _p5.table.setItem(r, _c, tp.QtWidgets.QTableWidgetItem(_v))


_poser(0, ["50", "800", "1000", "15", "0.8", "bon"])
_poser(1, ["60", "900", "1000", "15", "0.9", "bon aussi"])
_tons, _mauvaises = _p5._table_shades()
assert len(_tons) == 2 and not _mauvaises, ("table saine mal relue",
                                            len(_tons), _mauvaises)

# On blanchit UNE cellule, comme un doigt qui glisse sur un ton mesuré.
_p5.table.setItem(1, 2, tp.QtWidgets.QTableWidgetItem(""))
_tons, _mauvaises = _p5._table_shades()
assert _mauvaises == [2], ("la ligne illisible n'est pas signalée", _mauvaises)

# ET L'ENREGISTREMENT DOIT REFUSER, sans rien écrire.
_ecrits = []
_vrai_save = core.save_shades
try:
    core.save_shades = lambda m, s: _ecrits.append((m, list(s)))
    _ok = _p5.accept()
finally:
    core.save_shades = _vrai_save
assert _ok is False, ("le panneau accepte alors qu'une ligne est illisible : "
                      "le ton mesuré serait effacé")
assert not _ecrits, ("il a écrit malgré la ligne illisible", _ecrits)

# Corrigée, elle repasse -- sinon le refus serait un blocage, pas un garde.
_p5.table.setItem(1, 2, tp.QtWidgets.QTableWidgetItem("1000"))
try:
    core.save_shades = lambda m, s: _ecrits.append((m, list(s)))
    _ok = _p5.accept()
finally:
    core.save_shades = _vrai_save
assert _ok is True and len(_ecrits) == 1 and len(_ecrits[0][1]) == 2, (
    "une table saine devrait s'enregistrer", _ok, _ecrits)
print("5. le Nuancier refuse d'enregistrer une table qu'il ne sait pas "
      "relire, au lieu d'en effacer les tons OK")


# --- 6. UN RÉGLAGE TROUVÉ À L'ŒIL NE DOIT PAS SE PERDRE À LA FERMETURE ---
# La Calligraphie a perdu six réglages de plume pendant des semaines, le
# Marquage cinq champs de dégradé, puis deux du « ton sur mesure ». Chacun
# est une valeur cherchée à l'œil sur du bois, effacée par un clic sur la
# croix. Le balayage compare donc, panneau par panneau, les widgets de
# RÉGLAGE créés et ce que `_last_fields` mémorise.
#
# CHAQUE EXCLUSION EST NOMMÉE ET JUSTIFIÉE. Une liste d'exceptions muette
# finirait par tout absoudre -- et c'est exactement comme ça qu'un réglage
# se reperd.
_EXCLUS = {
    # Sélecteurs, pas des réglages : ils agissent puis se remettent au neutre.
    "combo_preset": "sélecteur de préréglages",
    "combo_police": "sélecteur qui remplit edt_police, lui mémorisé",
    "combo_recipe": "sélecteur d'objectif : le rejouer réappliquerait sa recette",
    # Persistés AILLEURS, et c'est le bon endroit.
    "chk_origin_bbox": "écrit dans save_settings au clic (réglage machine)",
    "spn_spot_dtest": "PER_LASER_KEYS, via save_settings",
    "spn_spot_focus": "PER_LASER_KEYS, via save_settings",
    "spn_spot_ztest": "PER_LASER_KEYS, via save_settings",
    "edt_measure_mat": "deuxième vue du matériau de ①, synchronisée",
    # Mesures et aides, pas des consignes.
    "spn_measured": "mesure au pied à coulisse, à refaire à chaque planche",
    "spn_dx": "résultat mesuré de la planche d'offset",
    "spn_dy": "résultat mesuré de la planche d'offset",
    "edt_mot": "loupe d'aperçu de la Calligraphie, pas un réglage gravé",
    # DÉLIBÉRÉMENT oublié : une hauteur défocalisée laissée derrière
    # empoisonne en silence tous les jobs suivants (défaut observé).
    "spn_cell_defocus": "remis au Z de travail à chaque objectif, exprès",
}
_src_tp = _lire("task_panels.py")
_classes = [(_m.start(), _m.group(1))
            for _m in re.finditer(r"^class (TaskPanel\w+)", _src_tp, re.M)]
_classes.append((len(_src_tp), "FIN"))
_perdus = []
for (_a, _nomp), (_b, _x) in zip(_classes, _classes[1:]):
    _bloc = _src_tp[_a:_b]
    _m = re.search(r"self\._last_fields\s*=\s*\{", _bloc)
    if not _m:
        continue
    _i = _m.end() - 1
    _prof, _j = 0, _i
    while _j < len(_bloc):
        if _bloc[_j] == "{":
            _prof += 1
        elif _bloc[_j] == "}":
            _prof -= 1
            if _prof == 0:
                break
        _j += 1
    _memo = set(re.findall(r"self\.(\w+)", _bloc[_i:_j]))
    _crees = set(re.findall(
        r"self\.(spn_\w+|combo_\w+|chk_\w+|edt_\w+)\s*=\s*QtWidgets\.", _bloc))
    for _w in sorted(_crees - _memo):
        if _w not in _EXCLUS:
            _perdus.append("{}.{}".format(_nomp, _w))
assert not _perdus, (
    "des réglages ne sont pas mémorisés et se perdront à la fermeture du "
    "panneau : les ajouter à _last_fields, ou les inscrire dans _EXCLUS "
    "avec la raison", _perdus)
print("6. tous les réglages des panneaux sont mémorisés ({} exclusions, "
      "chacune justifiée) OK".format(len(_EXCLUS)))


# --- 7. UN MODE PLAN DOIT REFUSER UNE FORME GALBÉE ----------------------
# Christophe, 05/08/2026 : un texte PROJETÉ sur une surface courbe, puis
# passé en Gravure remplie -- « l'aplat couleur n'a pas bien fonctionné,
# juste le point du i et l'intérieur du e sont colorés ».
#
# Ce n'était pas l'aperçu : `_faces_from_any_shape` est le MÊME constructeur
# que la Gravure remplie utilise pour savoir quoi hachurer, et il ne
# travaille qu'en 2D. Mesuré sur son document -- 1652 arêtes, 4 faces,
# 4,63 mm² -- et reproduit sur un cylindre de 60 mm : à plat 8 faces et
# 217,5 mm², projeté 2 faces et 0,0 mm². Le G-code serait sorti quasi
# blanc, sans un mot.
import FreeCAD                                                 # noqa: E402
import Part                                                    # noqa: E402

_d7 = FreeCAD.newDocument("EssaiPlan")
try:
    # Un carré bien plat, puis le même galbé de 0,3 mm -- l'ordre de grandeur
    # mesuré sur son cylindre.
    _plat = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0),
                              FreeCAD.Vector(20, 20, 0), FreeCAD.Vector(0, 20, 0),
                              FreeCAD.Vector(0, 0, 0)])
    assert core.ecart_au_plan(_plat) < 1e-6, (
        "un carré plat est vu comme galbé", core.ecart_au_plan(_plat))
    assert core.forme_est_plane(_plat)

    _galbe = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0),
                               FreeCAD.Vector(20, 20, 0.3),
                               FreeCAD.Vector(0, 20, 0), FreeCAD.Vector(0, 0, 0)])
    _e7 = core.ecart_au_plan(_galbe)
    assert 0.1 < _e7 < 0.5, ("le creux mesuré ne ressemble pas à celui d'une "
                             "projection", _e7)
    assert not core.forme_est_plane(_galbe), (
        "un creux de {:.2f} mm passe pour plan : c'est exactement le cas qui "
        "a vidé sa gravure".format(_e7))

    # LE SEUIL SE DÉDUIT DE LA FLÈCHE DE POLYGONISATION, il ne s'invente pas.
    assert abs(core.ECART_PLAN_MAXI_MM - 0.04) < 1e-9, (
        "le seuil de planéité a changé : il vaut deux fois la flèche de "
        "re-polygonisation (0,02 mm), en dessous de laquelle le constructeur "
        "de faces ne distingue plus rien", core.ECART_PLAN_MAXI_MM)

    # ET LE CAS DÉGÉNÉRÉ NE DOIT PAS CRIER AU LOUP : une forme alignée n'a
    # pas de plan à contredire.
    _ligne = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0),
                               FreeCAD.Vector(20, 0, 0)])
    assert core.forme_est_plane(_ligne), (
        "une forme alignée est déclarée galbée : le mode refuserait une "
        "sélection parfaitement valable")
finally:
    FreeCAD.closeDocument("EssaiPlan")
print("7. un creux de 0,3 mm est vu comme galbé, un carré plat et une ligne "
      "restent plans OK")


# --- 8. UN LIEN QUI SORT D'UN BODY DOIT ÊTRE UN XLink -------------------
# `App::PropertyLink` est à PORTÉE STRICTE. Le solide d'origine d'une
# projection vit presque toujours dans un Body ou une Part, et FreeCAD
# protestait donc à chaque recalcul -- « Link(s) to object(s) 'Pad' go out of
# the allowed scope [...] reside within 'Body' », deux fois par projection
# dans la vue Rapport de Christophe le 05/08/2026.
#
# Le lien FONCTIONNAIT : c'est un avertissement, pas une panne. Mais un
# avertissement qu'on apprend à ignorer finit par cacher celui qui compte.
_src_proj = _lire("laser_core.py")
_i8 = _src_proj.index("LaserAtelierSurfaceRef")
_avant8 = _src_proj[max(0, _i8 - 200):_i8]
assert "App::PropertyXLink" in _avant8, (
    "le lien vers le solide d'origine n'est pas un XLink : FreeCAD "
    "protestera à chaque recalcul dès que la surface vit dans un Body")

# ET L'APERÇU NE DOIT PAS SE PLAINDRE DEUX FOIS D'UNE SEULE CAUSE. Quand
# toutes les sources sont écartées parce qu'elles sont galbées, le message
# « ne délimite aucune surface fermée » accuse à tort le contour d'être
# ouvert -- en nommant le JOB, qui plus est.
_src_jobs = _lire("laser_jobs.py")
assert "if not galbees:" in _src_jobs, (
    "l'aperçu de calque redit « aucune surface fermée » après avoir déjà "
    "expliqué que la forme est galbée : deux messages pour une cause, et le "
    "second est faux")
print("8. le lien vers la surface traverse la portée, et l'aperçu ne se "
      "plaint qu'une fois par cause OK")


# --- 9. UN MODE QUI NE GRAVE PAS N'A PAS DE JOB -------------------------
# Un Job est un signet vers une GÉNÉRATION de G-code. Les Hachures n'en
# produisent aucun -- elles fabriquent une forme, que Marquage grave
# ensuite -- et pourtant elles s'en créaient un. Il ne pouvait rien faire :
# « mode non combinable » au job combiné, une case « Grave » sans objet, une
# couleur de calque sur une source qu'on ne grave pas.
#
# Christophe, 05/08/2026, après avoir enchaîné texte, remplissage, hachures,
# projection, contour puis job combiné : « je ne comprends pas le flux de
# travail [...] si ce n'est pas clair pour moi, cela ne le sera pas pour un
# nouvel utilisateur ». Projection, Texte, Texte gravé et Calligraphie
# fabriquent aussi des formes et n'ont JAMAIS créé de Job : les Hachures
# étaient l'exception.
import laser_jobs as _lj9                                      # noqa: E402

_d9 = FreeCAD.newDocument("EssaiFlux")
try:
    _o9 = _d9.addObject("Part::Feature", "Forme")
    _o9.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 0),
                                  FreeCAD.Vector(9, 0, 0)])
    _d9.recompute()
    assert _lj9.creer_ou_maj_job("hatch", [_o9]) is None, (
        "les Hachures se créent encore un Job, qui ne pourra rien graver")
    # ...mais un mode qui GRAVE doit toujours en créer un.
    assert _lj9.creer_ou_maj_job("curved", [_o9]) is not None, (
        "le Marquage ne crée plus de Job : le garde est trop large")

    # TOUT MODE DE GÉOMÉTRIE RESTE CONNU. Les documents déjà créés portent
    # des « Job Hachures » qu'il faut encore savoir nommer et rouvrir.
    for _m9 in _lj9.MODES_GEOMETRIE:
        assert _m9 in _lj9.MODES, (
            "« {} » a disparu de MODES : les Jobs des anciens documents "
            "perdraient leur nom et leur icône".format(_m9))

    # ET LE REFUS DOIT APPRENDRE QUELQUE CHOSE. « mode non combinable »
    # n'apprend rien à qui vient de passer une heure à préparer sa planche.
    _vieux = _d9.addObject("App::FeaturePython", "Job_hatch_ancien")
    _lj9.JobLaser(_vieux)
    _vieux.addProperty("App::PropertyString", "Mode", "Job", "")
    _vieux.Mode = "hatch"
    _vieux.addProperty("App::PropertyLinkList", "Sources", "Job", "")
    _vieux.Sources = [_o9]
    _vieux.Label = "Job Hachures - Forme"
    tp._COMBINED_OPS[:] = []
    _aj9, _ig9 = _lj9.ajouter_jobs_au_combine([_vieux])
    assert _aj9 == [] and _ig9, ("un ancien Job Hachures est passé", _aj9)
    assert "Marquage" in _ig9[0] and "FORME" in _ig9[0], (
        "le refus n'indique pas quoi faire à la place", _ig9[0])
finally:
    FreeCAD.closeDocument("EssaiFlux")
print("9. les modes de géométrie ne créent plus de Job, et le refus des "
      "anciens dit quoi faire OK")


# --- 10. UNE OPÉRATION COMBINÉE NE DOIT PAS VIEILLIR EN SILENCE ---------
# `_build_combined_operation` capture les arêtes ET les réglages au moment de
# l'ajout : une opération est un INSTANTANÉ. Modifier le job ensuite ne la
# touche pas. Christophe, 05/08/2026 : « j'ai changé un remplissage pour le
# mettre plus foncé, mais quand je vais dans les combinés, cela ne le prend
# pas en compte ». Il aurait gravé l'ancien réglage -- et ne l'aurait vu que
# sur le bois.
_d10 = FreeCAD.newDocument("EssaiCombine")
try:
    _o10 = _d10.addObject("Part::Feature", "Forme")
    _o10.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 0),
                                   FreeCAD.Vector(9, 0, 0)])
    _d10.recompute()
    _j10 = _lj9.creer_ou_maj_job("curved", [_o10])

    # LE LIEN VERS LE JOB EST CE QUI REND LA REPRISE POSSIBLE : sans lui, une
    # opération ne sait pas d'où elle vient.
    _ops = [{"type": "curved", "label": _j10.Label, "job": _j10.Name},
            {"type": "curved", "label": "ajoutée depuis son mode"},
            {"type": "curved", "label": "orpheline", "job": "Job_disparu"}]
    _appels = []
    _vrai_aj = _lj9.ajouter_jobs_au_combine
    try:
        _lj9.ajouter_jobs_au_combine = lambda jobs: (
            _appels.append([j.Name for j in jobs]), ([j.Label for j in jobs], []))[1]
        _repris, _laisses = _lj9.rafraichir_operations(_ops, _d10)
    finally:
        _lj9.ajouter_jobs_au_combine = _vrai_aj

    assert _appels == [[_j10.Name]], (
        "la reprise n'a pas interrogé le bon job", _appels)
    assert _repris == [_j10.Label], ("le job vivant n'a pas été repris", _repris)
    # LES DEUX AUTRES SONT NOMMÉS, PAS AVALÉS. Une opération gardée telle
    # quelle sans le dire, c'est exactement le défaut qu'on répare.
    assert len(_laisses) == 2, ("les opérations non reprises ne sont pas "
                                "nommées", _laisses)
    assert any("sans job" in _m for _m in _laisses), _laisses
    assert any("supprimé" in _m for _m in _laisses), _laisses
    assert len(_ops) == 3, ("la liste a changé de taille pendant la reprise",
                            len(_ops))

    # ET LA REPRISE DOIT AVOIR LIEU AVANT L'ÉCRITURE. Le dire après coup ne
    # réparerait rien : c'est le fichier qu'on grave qui doit être à jour.
    import inspect as _insp10
    _src10 = _insp10.getsource(tp.TaskPanelCombined._on_generer)
    _i_maj = _src10.find("_reprendre_reglages")
    _i_gen = _src10.find("generate_gcode_combined")
    assert 0 <= _i_maj < _i_gen, (
        "le job combiné écrit son G-code avant d'avoir repris les réglages "
        "des jobs", _i_maj, _i_gen)

    # ...ET DÈS L'OUVERTURE, sinon ce qu'on REGARDE ment. Christophe, après
    # avoir assombri un ton dans son job : « je vais voir dans le job
    # combiné et le rendu photo est toujours clair ». Protéger le fichier ne
    # suffit pas : un aperçu qui ne montre pas ce qu'on va obtenir donne la
    # confiance sans la justifier.
    _src_init = _insp10.getsource(tp.TaskPanelCombined.__init__)
    assert "_reprendre_reglages" in _src_init, (
        "le job combiné n'actualise ses opérations qu'à la génération : la "
        "liste, la durée, le trajet et l'aperçu photo montreront l'ancien "
        "réglage")
    # La reprise est PARTAGÉE, pas recopiée : deux copies divergeraient, et
    # c'est l'une des deux qui mentirait.
    assert _insp10.getsource(tp.TaskPanelCombined).count(
        "rafraichir_operations") == 1, (
        "la reprise est écrite deux fois dans le panneau : une seule des "
        "deux finira par être corrigée")
finally:
    FreeCAD.closeDocument("EssaiCombine")
print("10. le job combiné reprend les réglages des jobs avant d'écrire, et "
      "nomme les opérations qu'il garde telles quelles OK")


# --- 11. UN REPÈRE D'ORIGINE N'EST PAS UN MOTIF -------------------------
# Christophe, 05/08/2026 : un SVG importé, redimensionné sous Draft, posé sur
# sa surface, « j'ai voulu faire une projection et FreeCAD a crashé ».
#
# LE COUPABLE EST UN AXE D'ORIGINE. Les `App::Line` X/Y/Z d'un Body ont une
# épaisseur Z NULLE -- donc le classement les prenait pour des motifs 2D --
# et une longueur de 2e100 mm. `drop_edges_to_surface` les discrétise tous
# les PROJECTION_SAMPLE_DISTANCE millimètres : 2e100 points demandés. Mesuré
# sur l'interpréteur de FreeCAD : 10 millions de points en 2,1 s pour une
# arête de 10 000 km -- à 2e100, l'allocation ne revient jamais.
#
# Et ces axes sont VISIBLES par défaut dans un document PartDesign, donc
# cliquables : les attraper demande juste un clic un peu large.
_d11 = FreeCAD.newDocument("EssaiOrigine")
try:
    _axe = _d11.addObject("Part::Feature", "X_Axis")
    _axe.Shape = Part.LineSegment(FreeCAD.Vector(-1e100, 0, 0),
                                  FreeCAD.Vector(1e100, 0, 0)).toShape()
    _motif = _d11.addObject("Part::Feature", "MotifSVG")
    _motif.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 5),
                                     FreeCAD.Vector(9, 0, 5),
                                     FreeCAD.Vector(9, 9, 5),
                                     FreeCAD.Vector(0, 0, 5)])
    _surf = _d11.addObject("Part::Feature", "Pad")
    _surf.Shape = Part.makeBox(40, 40, 10, FreeCAD.Vector(-5, -5, -10))
    _d11.recompute()

    class _Sel11:
        def __init__(self, o):
            self.Object = o

    import time as _t11
    _t0 = _t11.time()
    _motifs, _ref = core.split_projection_selection(
        [_Sel11(_axe), _Sel11(_motif), _Sel11(_surf)])
    _dt = _t11.time() - _t0
    assert [m.Name for m in (_motifs or [])] == ["MotifSVG"], (
        "l'axe d'origine est encore pris pour un motif : la projection "
        "tentera de le discrétiser tous les millimètres sur 2e100 mm",
        [m.Name for m in (_motifs or [])])
    assert _ref is _surf, ("la surface n'est plus reconnue", _ref)
    # LE CLASSEMENT NE DOIT RIEN DISCRÉTISER : il écarte sur la boîte
    # englobante, donc il est instantané quelle que soit la démesure.
    assert _dt < 1.0, ("le classement s'attarde sur l'objet démesuré : il "
                       "en lit sans doute la géométrie", _dt)

    # ET LA PROJECTION COMPLÈTE DOIT ABOUTIR malgré l'axe dans la sélection.
    _t0 = _t11.time()
    _obj11, _err11 = core.run_projection(
        [_Sel11(_axe), _Sel11(_motif), _Sel11(_surf)])
    assert _obj11 is not None, ("la projection échoue alors que la sélection "
                                "contient un motif et une surface valables",
                                _err11)
    assert _t11.time() - _t0 < 10.0, "la projection s'éternise"

    # LE SEUIL EST LARGE EXPRÈS : une grande planche doit passer.
    assert core.TAILLE_MOTIF_MAXI_MM >= 5000.0, (
        "le seuil refuserait une planche de taille réaliste",
        core.TAILLE_MOTIF_MAXI_MM)
    _grand = _d11.addObject("Part::Feature", "GrandePlanche")
    _grand.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 5),
                                     FreeCAD.Vector(2000, 0, 5),
                                     FreeCAD.Vector(2000, 1000, 5),
                                     FreeCAD.Vector(0, 0, 5)])
    _d11.recompute()
    _m2, _r2 = core.split_projection_selection([_Sel11(_grand), _Sel11(_surf)])
    assert _m2 and _m2[0] is _grand, (
        "une planche de 2 m est refusée : le seuil est trop serré")
finally:
    FreeCAD.closeDocument("EssaiOrigine")
print("11. un axe d'origine (2e100 mm) est écarté sans être discrétisé, la "
      "projection aboutit, et une planche de 2 m passe encore OK")
