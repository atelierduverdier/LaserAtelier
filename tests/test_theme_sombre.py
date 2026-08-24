# -*- coding: utf-8 -*-
"""Les icônes doivent se voir sur un thème sombre.

Christophe, 24/08/2026 : « j'ai mis un thème sombre mais du coup je ne vois
plus les icônes de l'atelier laser ». Elles étaient toutes là, dessinées à
l'encre ardoise `#2f3540` de la charte -- sur un fond `#1a1e23` mesuré dans
sa palette. Contraste 1,4:1 : deux gris sombres l'un sur l'autre. Seul
l'orange surnageait, d'où des boutons réduits à un trait sans dessin autour
et des schémas de panneaux dont toutes les légendes avaient disparu.

CE DÉFAUT NE POUVAIT PAS ÊTRE VU PAR LE CODE, et c'est tout l'intérêt de le
geler ici. `test_barres_outils.py` vérifiait déjà que chaque bouton annonce
une icône, que le fichier existe et que son XML se parse -- les trois
passaient au vert pendant que la barre s'affichait vide. Un SVG parfaitement
valide dessiné dans la couleur du fond est indiscernable d'un SVG correct,
sauf à REGARDER l'écran ou à mesurer un contraste. On mesure.

Ce que ce fichier tient :

1. le contraste, dans les deux sens (le sombre gagne sans que le clair perde) ;
2. le seuil qui décide du thème ;
3. le jeu sombre est COMPLET (un nom manquant = un bouton vide) et son XML
   se parse -- QtSvg ne rend rien, en silence, sur un XML invalide ;
4. l'encre ardoise n'y subsiste nulle part, sauf là où c'est voulu ;
5. la liste des exceptions est à jour : aucune icône n'a pris un fond clair
   plein sans y être inscrite (c'est `workbench.svg` qui l'a, et l'éclaircir
   reviendrait à dessiner en clair sur du blanc) ;
6. fabriquer le jeu sombre ne touche pas au dépôt.
"""
import hashlib
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import preparer                                  # noqa: E402

h = preparer()
import icones                                                 # noqa: E402

SOURCE = icones._DOSSIER_SOURCE
FOND_SOMBRE = (0x1a, 0x1e, 0x23)     # mesuré dans la palette de Christophe
FOND_CLAIR = (0xef, 0xef, 0xef)      # le gris de fenêtre d'un thème clair


def contraste(rvb_a, rvb_b):
    """Rapport de contraste WCAG entre deux couleurs."""
    la, lb = icones._luminance(*rvb_a), icones._luminance(*rvb_b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def rvb(hexa):
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


# --- 1. LE CONTRASTE, DANS LES DEUX SENS ------------------------------
# Le seuil de 3:1 est celui que les recommandations d'accessibilité posent
# pour une FORME (un dessin, un pictogramme) -- pas pour du texte, qui en
# demande davantage. Une icône sous 3:1 n'est pas « discrète » : elle est
# absente.
_defaut = contraste(rvb(icones.ENCRE_CLAIRE), FOND_SOMBRE)
_corrige = contraste(rvb(icones.ENCRE_SOMBRE), FOND_SOMBRE)
_clair = contraste(rvb(icones.ENCRE_CLAIRE), FOND_CLAIR)

assert _defaut < 3.0, (
    "l'encre claire tiendrait sur fond sombre : ce fichier ne garde plus "
    "rien", _defaut)
assert _corrige >= 3.0, (
    "l'encre sombre ne se lit pas sur le fond mesuré", _corrige)
assert _clair >= 3.0, (
    "l'encre claire ne se lit plus sur un thème clair", _clair)
# LE JEU CLAIR NE DOIT RIEN PERDRE. C'est la raison d'être des deux jeux :
# une teinte moyenne unique tiendrait les deux fonds, mais à 3,8:1 partout,
# donc en délavant le thème clair, le manuel et le site (mêmes SVG, sur
# blanc). On vérifie que le clair garde une marge franche.
assert _clair >= 8.0, ("le jeu clair a perdu son mordant", _clair)
print("contraste : encre claire {:.1f}:1 sur fond sombre (le défaut), "
      "encre sombre {:.1f}:1, jeu clair conservé à {:.1f}:1 OK"
      .format(_defaut, _corrige, _clair))


# --- 2. LE SEUIL QUI DÉCIDE DU THÈME ----------------------------------
for fond, attendu in ((FOND_SOMBRE, True), (FOND_CLAIR, False),
                      ((0x30, 0x30, 0x30), True), ((0xd0, 0xd0, 0xd0), False)):
    icones.oublier_le_theme()
    icones._fond_du_theme = lambda f=fond: f
    assert icones.theme_sombre() is attendu, (fond, attendu)
    assert icones.encre() == (icones.ENCRE_SOMBRE if attendu
                              else icones.ENCRE_CLAIRE)
    assert icones.encre_douce() == (icones.ENCRE_DOUCE_SOMBRE if attendu
                                    else icones.ENCRE_DOUCE_CLAIRE)
print("seuil : 4 fonds classés du bon côté, encres assorties OK")


# --- 3 & 4 & 6. FABRICATION DU JEU SOMBRE ------------------------------
def empreinte(dossier):
    """Empreinte de tout un dossier d'icônes -- contenu ET liste."""
    m = hashlib.md5()
    for nom in sorted(os.listdir(dossier)):
        m.update(nom.encode("utf-8"))
        with open(os.path.join(dossier, nom), "rb") as f:
            m.update(f.read())
    return m.hexdigest()


_avant = empreinte(SOURCE)

_bac = tempfile.mkdtemp(prefix="laseratelier-icones-")
icones.oublier_le_theme()
icones._fond_du_theme = lambda: FOND_SOMBRE
icones._dossier_cache = lambda: _bac
_sombre = icones.dossier()

assert _sombre == _bac, ("le jeu sombre n'a pas été fabriqué", _sombre)
assert empreinte(SOURCE) == _avant, (
    "fabriquer le jeu sombre a MODIFIÉ les icônes du dépôt")
print("dépôt : les {} icônes sources sont intactes après fabrication OK"
      .format(len(os.listdir(SOURCE))))

_attendues = sorted(n for n in os.listdir(SOURCE) if n.endswith(".svg"))
_obtenues = sorted(n for n in os.listdir(_sombre) if n.endswith(".svg"))
assert _attendues == _obtenues, (
    "le jeu sombre n'a pas les mêmes icônes que la source : un nom absent "
    "donne un bouton vide",
    sorted(set(_attendues) ^ set(_obtenues)))

_illisibles, _restees_sombres = [], []
for nom in _obtenues:
    chemin = os.path.join(_sombre, nom)
    try:
        ET.parse(chemin)
    except Exception as exc:
        _illisibles.append((nom, str(exc)[:70]))
        continue
    with open(chemin, encoding="utf-8") as f:
        svg = f.read()
    if icones.ENCRE_CLAIRE in svg and nom not in icones.SANS_RETOUCHE:
        _restees_sombres.append(nom)

assert not _illisibles, (
    "la substitution a cassé un SVG : QtSvg ne rendra RIEN, en silence",
    _illisibles)
assert not _restees_sombres, (
    "des icônes gardent l'encre ardoise dans le jeu sombre", _restees_sombres)
print("jeu sombre : {} icônes, toutes présentes, XML valide, plus d'encre "
      "ardoise OK".format(len(_obtenues)))

# Les exclues sont recopiées TELLES QUELLES -- présentes, mais intactes.
for nom in icones.SANS_RETOUCHE:
    a = open(os.path.join(SOURCE, nom), encoding="utf-8").read()
    b = open(os.path.join(_sombre, nom), encoding="utf-8").read()
    assert a == b, ("{} devait être recopiée sans retouche".format(nom))
print("exceptions : {} recopiée(s) à l'identique OK"
      .format(", ".join(icones.SANS_RETOUCHE)))


# --- 5. LA LISTE DES EXCEPTIONS EST À JOUR -----------------------------
# Une icône qui peint SON PROPRE fond clair (un carré plein sous le dessin)
# doit garder l'encre foncée : l'éclaircir revient à dessiner en clair sur
# du blanc. `workbench.svg` est dans ce cas. Le jour où une nouvelle icône
# prend ce parti, elle sera éclaircie en silence et deviendra illisible dans
# le sélecteur d'atelier -- exactement le défaut d'aujourd'hui, à l'envers.
_RECT = re.compile(r"<rect\b[^>]*>")
_ATTR = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')


def peint_un_fond_clair(svg):
    for balise in _RECT.findall(svg):
        a = dict(_ATTR.findall(balise))
        try:
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
            larg, haut = float(a.get("width", 0)), float(a.get("height", 0))
        except ValueError:
            continue
        fill = a.get("fill", "")
        if not (x <= 2 and y <= 2 and larg >= 60 and haut >= 60):
            continue
        if fill.startswith("#") and len(fill.lstrip("#")) == 6:
            if icones._luminance(*rvb(fill)) > icones.SEUIL_SOMBRE:
                return fill
    return None


_a_declarer = []
for nom in _attendues:
    with open(os.path.join(SOURCE, nom), encoding="utf-8") as f:
        fond = peint_un_fond_clair(f.read())
    if fond and nom not in icones.SANS_RETOUCHE:
        _a_declarer.append((nom, fond))

assert not _a_declarer, (
    "ces icônes peignent leur propre fond clair et seraient éclaircies à "
    "tort : les inscrire dans icones.SANS_RETOUCHE", _a_declarer)
# Et l'inverse : une exception qui n'a plus lieu d'être délave une icône
# pour rien.
_inutiles = [n for n in icones.SANS_RETOUCHE
             if not peint_un_fond_clair(
                 open(os.path.join(SOURCE, n), encoding="utf-8").read())]
assert not _inutiles, (
    "ces icônes n'ont plus de fond clair : les retirer de SANS_RETOUCHE",
    _inutiles)
print("exceptions : la liste couvre exactement les icônes à fond clair OK")


# --- 7. UN NOM INCONNU NE RENVOIE PAS UN CHEMIN MORT -------------------
assert icones.chemin("workbench.svg") == os.path.join(_sombre, "workbench.svg")
assert icones.chemin("pas_encore_dessinee.svg") == os.path.join(
    SOURCE, "pas_encore_dessinee.svg"), (
    "une icône absente du cache doit retomber sur la source")
print("repli : une icône absente du cache retombe sur la source OK")


# --- 8. LE JEU CLAIR RESTE LE DOSSIER DU DÉPÔT -------------------------
icones.oublier_le_theme()
icones._fond_du_theme = lambda: FOND_CLAIR
assert icones.dossier() == SOURCE, (
    "sur thème clair, rien ne doit être fabriqué", icones.dossier())
print("thème clair : aucun cache fabriqué, on lit le dépôt OK")
