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
