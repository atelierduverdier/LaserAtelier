# -*- coding: utf-8 -*-
"""icones.py -- le jeu d'icônes accordé au thème de FreeCAD.

© Atelier du Verdier -- licence LGPL-2.1-or-later (cf. LICENSE).

Christophe, 24/08/2026 : « j'ai mis un thème sombre mais du coup je ne vois
plus les icônes de l'atelier laser ». Elles étaient bien là. La charte de
l'atelier dessine à l'ENCRE ARDOISE `#2f3540` sur fond clair ; le fond du
thème sombre, MESURÉ sur sa machine (palette de la fenêtre principale, thème
PrintNC), vaut `#1a1e23`. Deux gris sombres presque confondus : 1,4:1 de
contraste, là où il en faut 3 pour qu'une forme se lise. Seul l'orange
`#ff8a00` surnageait -- d'où des boutons réduits à un trait orange sans
dessin autour, et des schémas de panneaux dont les légendes disparaissaient
entièrement.

POURQUOI DEUX JEUX, ET PAS UNE SEULE COULEUR QUI IRAIT AUX DEUX FONDS.
La question mérite d'être posée, parce que la réponse n'est pas celle qu'on
croit : une teinte moyenne PEUT servir les deux. En luminance relative
(WCAG), il faut L >= 0,138 pour tenir 3:1 sur `#1a1e23`, et L <= 0,255 pour
tenir 3:1 sur le `#efefef` d'un thème clair. La fenêtre existe : `#797f8c`
s'y loge et donne 3,8:1 de chaque côté. Elle a été écartée pour ce qu'elle
COÛTE : les icônes tombent de 10,7:1 à 3,8:1 sur fond clair -- un délavé
permanent sur le thème clair, sur les captures du manuel et sur le site (les
mêmes SVG sont recopiés dans `docs/assets/`, toujours sur blanc) -- et sans
jamais dépasser 3,8:1 sur fond sombre. Deux jeux gardent les 10,7:1 du clair
et donnent 11,0:1 sur le sombre.

LE JEU SOMBRE EST FABRIQUÉ, PAS RECOPIÉ. Quatre-vingts fichiers jumeaux dans
le dépôt divergeraient au premier ajustement d'icône, exactement comme la
ligne VERSION recopiée à la main est restée 44 versions en retard. Une seule
substitution de couleur suffit : on l'applique au vol, dans un dossier de
cache, et le dépôt ne connaît qu'un seul jeu.

CE QUI N'EST PAS RETOUCHÉ, et pourquoi :

- `workbench.svg` peint SON PROPRE fond blanc (un carré arrondi plein) : son
  encre doit rester sombre, sinon on éclaircit un dessin posé sur du blanc.
  `tests/test_theme_sombre.py` vérifie qu'aucune autre icône n'a pris ce
  genre de fond depuis.
- LE CHAPEAU, la signature de l'atelier -- éclairci il devient un melon
  blanc qui n'est plus celui de la maison, et il n'a pas besoin de l'être :
  ses deux reflets blancs dessinent sa silhouette. Il est écarté de deux
  façons parce qu'il se présente de deux façons : par sa marque de groupe
  `class="chapeau-verdier"` dans les 24 icônes de mode, et par son nom pour
  `chapeau.svg`, le fichier qui ne contient QUE lui (`SIGNATURE`).
- Les orangés, jaunes, rouges et verts : ce sont des DONNÉES, pas de l'encre.
  Le dégradé du nuancier (`#ffe3c2` -> `#a85a00`) et les carrés brûlés de la
  grille d'essai (`#ffd400` -> `#3a0509`) racontent une échelle de tons ;
  les inverser mentirait sur ce qu'ils montrent. Ils se lisent déjà sur fond
  sombre.

Le thème est lu UNE fois, paresseusement, à la première icône demandée --
c'est-à-dire quand Christophe active l'atelier, bien après que FreeCAD a
posé sa feuille de style. Changer de thème demande donc un redémarrage de
FreeCAD, comme pour la plupart des réglages d'apparence.

Rien ici n'a le droit d'empêcher l'atelier de s'ouvrir : à la moindre
exception on retombe sur le jeu d'origine (icônes peu lisibles, mais
présentes), jamais sur une erreur.
"""
import hashlib
import inspect
import os
import re

_DOSSIER_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "resources", "icons")

# L'ardoise de la charte, et son reflet pour fond sombre.
ENCRE_CLAIRE = "#2f3540"
ENCRE_SOMBRE = "#c9d2e0"

# L'encre atténuée des libellés secondaires (« identique à celle du panneau »,
# le numéro de version sous le titre) : même écart au fond, en plus discret.
ENCRE_DOUCE_CLAIRE = "#5a626e"
ENCRE_DOUCE_SOMBRE = "#98a1b0"

# Icônes qui peignent leur propre fond clair : les retoucher les abîmerait.
SANS_RETOUCHE = ("workbench.svg",)

# Le chapeau seul. C'est la SIGNATURE de l'atelier, pas un trait de dessin :
# elle garde son ardoise sur les deux thèmes (cf. `_eclaircir`). Ce fichier-ci
# n'est que le chapeau, sans dessin autour et sans la marque de groupe qui le
# désigne dans les autres icônes -- il faut donc l'écarter par son nom. Il
# n'est pas décoratif : `_panel_header` le pose à 22 px dans l'en-tête de
# CHAQUE panneau de l'atelier.
SIGNATURE = ("chapeau.svg",)

# Sous ce seuil de luminance relative, le fond est « sombre ». 0,18 tombe
# vers `#797979`, le gris moyen : au-dessus on dessine à l'encre foncée,
# au-dessous à l'encre claire.
SEUIL_SOMBRE = 0.18

_theme_sombre = None       # None = pas encore regardé
_dossier = None


def _luminance(r, v, b):
    """Luminance relative WCAG d'un RVB donné en 0-255."""
    def _lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(v) + 0.0722 * _lin(b)


def _fond_du_theme():
    """La couleur de fond de l'interface, ou None si on ne peut pas la lire.

    La fenêtre principale d'abord (c'est elle que la feuille de style
    habille, et c'est déjà elle que `InitGui._colorer_barres` interroge pour
    teinter les barres) ; l'application ensuite, pour les tests headless."""
    try:
        from PySide6 import QtGui, QtWidgets
        palette = None
        try:
            import FreeCADGui
            fen = FreeCADGui.getMainWindow()
            if fen is not None:
                palette = fen.palette()
        except Exception:
            palette = None
        if palette is None:
            app = QtWidgets.QApplication.instance()
            if app is None:
                return None
            palette = app.palette()
        c = palette.color(QtGui.QPalette.Window)
        return (c.red(), c.green(), c.blue())
    except Exception:
        return None


def theme_sombre():
    """Vrai si l'interface est sur fond sombre. Lu une fois, puis retenu."""
    global _theme_sombre
    if _theme_sombre is None:
        fond = _fond_du_theme()
        if fond is None:
            # ON NE RETIENT PAS UNE RÉPONSE QU'ON N'A PAS EUE. Sans palette
            # lisible -- Qt pas encore levé, exécution sans interface -- on
            # rend « clair » pour cette fois, mais on regardera de nouveau
            # au prochain appel : mémoriser cette non-réponse fixerait le
            # thème pour toute la session sur une lecture qui a échoué.
            return False
        _theme_sombre = _luminance(*fond) < SEUIL_SOMBRE
    return _theme_sombre


def encre():
    """La couleur d'encre lisible sur le thème courant."""
    return ENCRE_SOMBRE if theme_sombre() else ENCRE_CLAIRE


def encre_douce():
    """L'encre atténuée lisible sur le thème courant."""
    return ENCRE_DOUCE_SOMBRE if theme_sombre() else ENCRE_DOUCE_CLAIRE


def _dossier_cache():
    """Où poser le jeu sombre. Le dossier de données de FreeCAD, comme la
    config -- mais dans un sous-dossier à part : `laser_atelier_config.json`
    porte des mesures d'établi et ne partage rien avec un cache jetable."""
    try:
        import FreeCAD
        return os.path.join(FreeCAD.getUserAppDataDir(), "LaserAtelier",
                            "icones_sombres")
    except Exception:
        import tempfile
        return os.path.join(tempfile.gettempdir(), "laseratelier-icones-sombres")


# L'EMPREINTE DE LA RECETTE, et non des seules sources. Le cache ne se
# refaisait qu'au vu de la DATE des SVG : changer la règle de substitution
# -- les couleurs, les listes d'exclusion, ou le code d'`_eclaircir` -- ne
# le périmait pas, et l'ancien jeu survivait indéfiniment.
#
# Ce n'est pas théorique : la v2.99.42 a précisément modifié `_eclaircir`
# pour épargner le chapeau. Quiconque avait déjà un cache gardait donc son
# melon blanc APRÈS le correctif, sans que rien ne le dise -- le défaut que
# Christophe avait signalé serait resté sous ses yeux.
#
# On prend l'empreinte du CODE lui-même : toute retouche de la règle
# invalide le cache, sans qu'on ait à y penser.
NOM_RECETTE = "recette.txt"


def _empreinte_recette():
    morceaux = [ENCRE_CLAIRE, ENCRE_SOMBRE, repr(SANS_RETOUCHE), repr(SIGNATURE)]
    for fonction in (_eclaircir, _bornes_chapeau):
        try:
            morceaux.append(inspect.getsource(fonction))
        except (OSError, TypeError):
            morceaux.append(fonction.__name__)
    return hashlib.sha256("\n".join(morceaux).encode("utf-8")).hexdigest()[:16]


_MARQUE_CHAPEAU = 'class="chapeau-verdier"'
_BALISE_G = re.compile(r"<g\b[^>]*?(/?)>|</g>")


def _bornes_chapeau(svg):
    """(début, fin) du groupe de signature dans le texte du SVG, ou None.

    On borne le groupe des DEUX côtés au lieu de trancher jusqu'à la fin du
    fichier. Le chapeau est aujourd'hui le dernier élément des 24 icônes qui
    le portent -- mesuré -- mais rien ne l'impose : le jour où un dessin
    passe après lui, une découpe « du chapeau à la fin » laisserait ce
    dessin à l'ardoise, donc invisible sur fond sombre, sans un mot. Et le
    test aurait eu le même angle mort que le code, ce qui est la manière
    connue de fabriquer une mire qui ne peut pas voir le défaut qu'elle
    surveille.
    """
    if _MARQUE_CHAPEAU not in svg:
        return None
    debut = svg.rindex("<g", 0, svg.index(_MARQUE_CHAPEAU))
    profondeur = 0
    for m in _BALISE_G.finditer(svg, debut):
        if m.group(0).startswith("</"):
            profondeur -= 1
        elif m.group(1):          # <g ... /> : ouvert et refermé d'un coup
            continue
        else:
            profondeur += 1
        if profondeur == 0:
            return debut, m.end()
    return debut, len(svg)        # groupe non refermé : XML cassé de toute façon


def _eclaircir(svg):
    """Passe l'encre en clair — SAUF le chapeau.

    Christophe, 25/08/2026 : « mon petit chapeau sur les icônes est blanc au
    lieu de noir ». Le chapeau est une SIGNATURE, pas un trait de dessin :
    éclairci, il devient un melon blanc qui n'est plus celui de l'atelier. Et
    il n'a pas besoin de l'être — ses deux reflets blancs dessinent sa
    silhouette, donc il reste parfaitement lisible sur `#1a1e23` en gardant son
    ardoise d'origine. Vérifié à l'œil sur les trois traitements possibles :
    éclairci (melon blanc), intact (lisible, retenu), intact sans les reflets
    (la calotte se noie dans le fond).
    """
    bornes = _bornes_chapeau(svg)
    if bornes is None:
        return svg.replace(ENCRE_CLAIRE, ENCRE_SOMBRE)
    debut, fin = bornes
    return (svg[:debut].replace(ENCRE_CLAIRE, ENCRE_SOMBRE)
            + svg[debut:fin]
            + svg[fin:].replace(ENCRE_CLAIRE, ENCRE_SOMBRE))


def fabriquer(destination, source=None):
    """Recopie le jeu d'icônes en remplaçant l'encre. Renvoie le dossier écrit.

    Un fichier n'est réécrit que s'il manque ou s'il est plus vieux que sa
    source : au démarrage suivant, plus rien à faire. Les icônes de
    `SANS_RETOUCHE` et de `SIGNATURE` sont copiées telles quelles -- elles
    doivent exister dans le jeu sombre aussi, sinon le bouton s'affiche vide."""
    source = source or _DOSSIER_SOURCE
    os.makedirs(destination, exist_ok=True)
    empreinte = _empreinte_recette()
    marque = os.path.join(destination, NOM_RECETTE)
    try:
        with open(marque, "r", encoding="utf-8") as f:
            meme_recette = f.read().strip() == empreinte
    except OSError:
        meme_recette = False
    for nom in sorted(os.listdir(source)):
        if not nom.endswith(".svg"):
            continue
        src = os.path.join(source, nom)
        dst = os.path.join(destination, nom)
        if (meme_recette and os.path.exists(dst)
                and os.path.getmtime(dst) >= os.path.getmtime(src)):
            continue
        with open(src, "r", encoding="utf-8") as f:
            svg = f.read()
        if nom not in SANS_RETOUCHE and nom not in SIGNATURE:
            svg = _eclaircir(svg)
        # Écriture par fichier temporaire puis renommage : une session
        # FreeCAD qui lit pendant qu'une autre écrit ne doit jamais tomber
        # sur un SVG à moitié posé (QtSvg ne rendrait rien, en silence).
        temporaire = dst + ".part"
        with open(temporaire, "w", encoding="utf-8") as f:
            f.write(svg)
        os.replace(temporaire, dst)
    # La marque est posée EN DERNIER : une fabrication interrompue laisse
    # une recette absente ou périmée, donc un cache qui se refera.
    temporaire = marque + ".part"
    with open(temporaire, "w", encoding="utf-8") as f:
        f.write(empreinte)
    os.replace(temporaire, marque)
    return destination


def dossier():
    """Le dossier d'icônes à utiliser pour le thème courant."""
    global _dossier
    if _dossier is None:
        _dossier = _DOSSIER_SOURCE
        if theme_sombre():
            try:
                _dossier = fabriquer(_dossier_cache())
            except Exception as exc:
                try:
                    import FreeCAD
                    FreeCAD.Console.PrintLog(
                        "LaserAtelier : jeu d'icônes sombre non fabriqué "
                        "({}), on garde le jeu clair.\n".format(exc))
                except Exception:
                    pass
                _dossier = _DOSSIER_SOURCE
    return _dossier


def chemin(nom):
    """Le chemin de l'icône `nom` dans le jeu accordé au thème."""
    fichier = os.path.join(dossier(), nom)
    # Une icône ajoutée après la fabrication du cache : on se rabat sur la
    # source plutôt que de renvoyer un chemin qui n'existe pas.
    if not os.path.exists(fichier):
        return os.path.join(_DOSSIER_SOURCE, nom)
    return fichier


def oublier_le_theme():
    """Oublie le thème retenu (tests : rejouer les deux cas d'affilée)."""
    global _theme_sombre, _dossier
    _theme_sombre = None
    _dossier = None
