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
4. l'encre ardoise n'y subsiste nulle part, sauf là où c'est voulu -- et
   la substitution a bien eu lieu, autant de fois qu'il y avait d'ardoise ;
5. LE CHAPEAU garde son ardoise, encre pour encre, dans les 24 icônes qui le
   portent comme dans `chapeau.svg` qui n'est que lui ;
6. la liste des exceptions est à jour : aucune icône n'a pris un fond clair
   plein sans y être inscrite (c'est `workbench.svg` qui l'a, et l'éclaircir
   reviendrait à dessiner en clair sur du blanc) ;
7. fabriquer le jeu sombre ne touche pas au dépôt.
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


# --- 3 & 4 & 5 & 7. FABRICATION DU JEU SOMBRE ------------------------------
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

def _encres(noeud, couleur, dedans=False):
    """Combien de fois `couleur` sert d'encre : HORS du chapeau, puis DEDANS.

    ON MARCHE SUR L'ARBRE, PAS SUR LE TEXTE DU FICHIER. Découper la chaîne
    « du chapeau jusqu'à la fin » aurait donné à ce test exactement l'angle
    mort du code qu'il surveille : un dessin ajouté APRÈS le groupe de
    signature resterait à l'ardoise, invisible sur fond sombre, et le
    contrôle passerait au vert. Ce dépôt a déjà payé une mire porteuse du
    même défaut que la chaîne qu'elle devait valider.
    """
    dedans = dedans or noeud.get("class") == "chapeau-verdier"
    n = sum(1 for a in ("fill", "stroke", "style")
            if couleur in (noeud.get(a) or ""))
    hors, sous = (0, n) if dedans else (n, 0)
    for fils in noeud:
        h, d = _encres(fils, couleur, dedans)
        hors += h
        sous += d
    return hors, sous


_intactes = tuple(icones.SANS_RETOUCHE) + tuple(icones.SIGNATURE)
_illisibles, _restees_sombres = [], []
_chapeaux_touches, _mal_substituees = [], []
for nom in _obtenues:
    chemin = os.path.join(_sombre, nom)
    try:
        racine = ET.parse(chemin).getroot()
    except Exception as exc:
        _illisibles.append((nom, str(exc)[:70]))
        continue
    if nom in _intactes:
        continue
    source = ET.parse(os.path.join(SOURCE, nom)).getroot()
    ardoise_hors_src, ardoise_sous_src = _encres(source, icones.ENCRE_CLAIRE)
    ardoise_hors, ardoise_sous = _encres(racine, icones.ENCRE_CLAIRE)
    clair_hors, clair_sous = _encres(racine, icones.ENCRE_SOMBRE)
    if ardoise_hors:
        _restees_sombres.append((nom, ardoise_hors))
    # La substitution a bien EU LIEU, et exactement autant de fois : une
    # icône dont plus rien ne serait remplacé passerait le contrôle
    # ci-dessus sans avoir rien fait.
    if clair_hors != ardoise_hors_src:
        _mal_substituees.append((nom, ardoise_hors_src, clair_hors))
    # ... et l'inverse : le chapeau garde son ardoise, encre pour encre.
    if (ardoise_sous, clair_sous) != (ardoise_sous_src, 0):
        _chapeaux_touches.append((nom, ardoise_sous_src, ardoise_sous,
                                  clair_sous))

assert not _illisibles, (
    "la substitution a cassé un SVG : QtSvg ne rendra RIEN, en silence",
    _illisibles)
assert not _restees_sombres, (
    "des icônes gardent l'encre ardoise dans le jeu sombre", _restees_sombres)
assert not _mal_substituees, (
    "l'encre n'a pas été remplacée le bon nombre de fois (nom, attendu, obtenu)",
    _mal_substituees)
# Christophe, 25/08/2026 : « mon petit chapeau sur les icônes est blanc au lieu
# de noir ». Le chapeau est une SIGNATURE, pas un trait de dessin : éclairci il
# devient un melon blanc qui n'est plus celui de l'atelier. Il n'a pas besoin de
# l'être -- ses deux reflets blancs dessinent sa silhouette, donc il reste
# lisible sur #1a1e23 en gardant son ardoise. Vérifié à l'œil sur les trois
# traitements : éclairci (melon blanc), intact (retenu), intact sans reflets
# (la calotte se noie).
assert not _chapeaux_touches, (
    "le chapeau de signature a été retouché : il doit garder son ardoise "
    "(nom, ardoise attendue, ardoise obtenue, encre claire posée)",
    _chapeaux_touches)
_avec_chapeau = sum(1 for n in _obtenues if n not in _intactes
                    and _encres(ET.parse(os.path.join(SOURCE, n)).getroot(),
                                icones.ENCRE_CLAIRE)[1])
assert _avec_chapeau >= 20, (
    "presque plus aucune icône ne porte le chapeau : le contrôle ci-dessus "
    "ne contrôle plus rien", _avec_chapeau)
print("jeu sombre : {} icônes, toutes présentes, XML valide, encre éclaircie "
      "hors chapeau, chapeau intact sur les {} qui le portent OK"
      .format(len(_obtenues), _avec_chapeau))

# Les exclues sont recopiées TELLES QUELLES -- présentes, mais intactes.
# `SIGNATURE` en fait partie : `chapeau.svg` ne contient QUE le chapeau, donc
# sans le groupe marqué qui le désigne ailleurs -- il faut l'écarter par son
# nom. Ce n'est pas un fichier décoratif : `_panel_header` le pose à 22 px
# dans l'en-tête de CHAQUE panneau de l'atelier, et c'est là que le melon
# blanc se voyait.
for nom in _intactes:
    a = open(os.path.join(SOURCE, nom), encoding="utf-8").read()
    b = open(os.path.join(_sombre, nom), encoding="utf-8").read()
    assert a == b, ("{} devait être recopiée sans retouche".format(nom))
# Une exception par son nom n'a de sens que si le fichier porte vraiment de
# l'ardoise ET pas la marque de groupe : sinon la règle générale suffirait,
# et cette ligne-ci délave... rien, en silence.
for nom in icones.SIGNATURE:
    src = open(os.path.join(SOURCE, nom), encoding="utf-8").read()
    assert icones.ENCRE_CLAIRE in src, (
        "{} n'a plus d'encre ardoise : l'écarter ne sert plus à rien"
        .format(nom))
    assert 'class="chapeau-verdier"' not in src, (
        "{} porte désormais la marque de groupe : la retirer de "
        "icones.SIGNATURE, la règle générale suffit".format(nom))
print("exceptions : {} recopiée(s) à l'identique OK"
      .format(", ".join(_intactes)))


# --- 5b. CE QUI SUIT LE CHAPEAU EST ÉCLAIRCI AUSSI --------------------
# Dans les 24 icônes d'aujourd'hui le chapeau est le DERNIER élément, si
# bien qu'une découpe « du chapeau jusqu'à la fin du fichier » donne le bon
# résultat -- et qu'aucune icône du dépôt ne peut distinguer les deux
# versions du code. La propriété se gèle donc sur un cas fabriqué : un
# dessin APRÈS la signature. Sans lui, revenir à la découpe paresseuse ne
# ferait rougir aucun contrôle, et le premier dessin posé sous le chapeau
# serait invisible sur fond sombre sans un mot.
_ESSAI = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<path stroke="{ardoise}" d="M0 0 L8 8"/>'
    '<g class="chapeau-verdier"><g><path fill="{ardoise}" d="M1 1 L2 2"/>'
    '</g></g>'
    '<path stroke="{ardoise}" d="M9 9 L16 16"/>'
    '</svg>').format(ardoise=icones.ENCRE_CLAIRE)
_rendu = icones._eclaircir(_ESSAI)
_apres_chapeau = _rendu[_rendu.index("</g></g>") + len("</g></g>"):]
assert icones.ENCRE_CLAIRE not in _apres_chapeau, (
    "un dessin placé APRÈS le chapeau garde l'encre ardoise : il sera "
    "invisible sur fond sombre", _apres_chapeau)
assert _rendu.count(icones.ENCRE_SOMBRE) == 2, (
    "les deux traits hors chapeau devaient être éclaircis", _rendu)
assert _rendu.count(icones.ENCRE_CLAIRE) == 1, (
    "le chapeau devait garder son unique encre ardoise", _rendu)
# Et un chapeau qui n'est pas refermé ne doit pas faire tomber la fabrication
# en marche : à la moindre exception, l'atelier perdrait tout son jeu sombre.
icones._eclaircir(_ESSAI.replace("</g></g>", ""))
print("chapeau : ce qui le précède ET ce qui le suit est éclairci, lui non OK")


# --- 6. LA LISTE DES EXCEPTIONS EST À JOUR -----------------------------
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


# --- 8. UN NOM INCONNU NE RENVOIE PAS UN CHEMIN MORT -------------------
assert icones.chemin("workbench.svg") == os.path.join(_sombre, "workbench.svg")
assert icones.chemin("pas_encore_dessinee.svg") == os.path.join(
    SOURCE, "pas_encore_dessinee.svg"), (
    "une icône absente du cache doit retomber sur la source")
print("repli : une icône absente du cache retombe sur la source OK")


# --- 9. LE JEU CLAIR RESTE LE DOSSIER DU DÉPÔT -------------------------
icones.oublier_le_theme()
icones._fond_du_theme = lambda: FOND_CLAIR
assert icones.dossier() == SOURCE, (
    "sur thème clair, rien ne doit être fabriqué", icones.dossier())
print("thème clair : aucun cache fabriqué, on lit le dépôt OK")
