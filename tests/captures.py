# -*- coding: utf-8 -*-
"""Régénère les captures de panneaux du manuel et de la galerie du site.

    python3 tests/lancer.py --captures          # tout
    python3 tests/lancer.py --captures halftone # un panneau

Se lance comme un test (même interpréteur FreeCAD, même harnais), et c'est
tout l'intérêt : la config est redirigée vers une COPIE jetable, donc capturer
ne peut pas écrire dans les mesures au pied à coulisse de l'atelier. L'ancienne
méthode pilotait la session FreeCAD ouverte de Christophe, avec sa vraie
config sous la main et ses panneaux qui s'ouvraient sous ses yeux.

Deux pièges hérités de cette ancienne méthode, à ne pas re-découvrir :

- `sizeHint` des panneaux est inutilisable (toujours ~408 px). On force donc
  une largeur de 430 et une hauteur généreuse, puis on recadre.
- `WA_DontShowOnScreen` est OBLIGATOIRE : sans lui le gestionnaire de fenêtres
  écrête la hauteur à ~900 px. Le vrai layout est sur `w.widget()`, pas sur
  `w.layout()` (None sur une QScrollArea).

N'essaie PAS de déplier les sections pour la galerie (`set_open(True)` sur
chaque `_SectionHeader`) : piloté de l'extérieur, le basculement laisse le
CHEVRON et la visibilité des rangées désynchronisés -- on obtient des barres
marquées « repliée » (▸) au-dessus d'un contenu visible, et un panneau plus
COURT que son état par défaut. Essayé le 30/07/2026, image à l'appui. Chaque
panneau est donc capturé dans l'état où il s'ouvre vraiment, ce qui est aussi
ce que l'utilisateur voit.

Et le recadrage du bas se fait en scannant la LARGEUR COMPLÈTE de chaque
rangée : un échantillonnage à quelques colonnes rate le texte qui ne les
touche pas et coupe des phrases en cours (vécu sur le Guide rapide, « …lunettes
laser » tronqué avant « sur le nez »).
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_MANUEL = os.path.join(RACINE, "docs", "manuel_img")
IMG_SITE = os.path.join(RACINE, "docs", "screenshots", "panneaux")

# nom manuel -> (classe, hauteur du crop, fichier de galerie)
# La hauteur est réglée panneau par panneau : 760 par défaut, moins pour les
# panneaux courts (760 y laisserait un grand blanc).
PANNEAUX = [
    ("guide",      "TaskPanelGuide",           760, "01_guide"),
    ("hatch",      "TaskPanelHatch",           480, "02_hachures_2d"),
    ("filled",     "TaskPanelFilledEngraving", 760, "03_gravure_remplie"),
    ("halftone",   "TaskPanelHalftone",        760, "04_gravure_photo"),
    ("project",    "TaskPanelProject",         480, "05_projection"),
    ("curved",     "TaskPanelCurved",          760, "06_marquage"),
    ("curvedcut",  "TaskPanelCurvedCut",       760, "07_decoupe_courbe"),
    ("flat",       "TaskPanelFlat",            760, "08_decoupe_plate"),
    ("kerf",       "TaskPanelKerf",            480, "09_calibration_kerf"),
    ("testgrid",   "TaskPanelTestGrid",        760, "10_grille_test"),
    ("powerramp",  "TaskPanelPowerRamp",       760, "11_rampe_puissance"),
    ("defocus",    "TaskPanelDefocusCalibration", 760, "12_calibration_defocus"),
    ("offset",     "TaskPanelOffsetTest",      760, "13_test_offsets"),
    ("nuancier",   "TaskPanelNuancier",        760, "14_nuancier"),
    ("combined",   "TaskPanelCombined",        760, "15_job_combine"),
    ("settings",   "TaskPanelSettings",        540, "16_preferences"),
    ("assistant",  "TaskPanelAssistant",       760, "17_assistant"),
    ("text",       "TaskPanelText",            240, "18_text"),
    ("catalogue",  "TaskPanelCatalogue",       760, "19_catalogue"),
    # Import SVG : mode ajouté en v1.78.0, jamais illustré. Numéroté 20 pour
    # ne pas renuméroter les dix-neuf autres ; sa place dans la galerie est
    # donnée par panneaux.md, pas par le chiffre du fichier.
    ("importsvg",  "TaskPanelImportSVG",       480, "20_import_svg"),
]

LARGEUR = 430
HAUTEUR_MAX = 3600


def _autocrop_bas(img, fond):
    """Dernière rangée non vide, en scannant TOUTE la largeur."""
    from PySide6 import QtGui   # noqa: F401  (import tardif, après QApplication)
    h, w = img.height(), img.width()
    dernier = 0
    for y in range(h):
        vide = True
        for x in range(0, w, 2):
            if img.pixel(x, y) != fond:
                vide = False
                break
        if not vide:
            dernier = y
    return dernier


def _stabiliser(app, inner):
    """Fige la mise en page AVANT de photographier.

    `adjustSize()` rétrécit le conteneur à son sizeHint -- donc les
    paragraphes deviennent PLUS ÉTROITS qu'à la largeur pour laquelle ils
    venaient de figer leur hauteur minimale. Il leur faut alors plus de
    lignes que de place : le texte débordait sur la rangée suivante, et
    l'image partait au manuel et au site avec des phrases écrites l'une
    sur l'autre (constaté le 03/08/2026 sur la Bande de calibration :
    « ★ Étape 1/4… » recouvrait « 1. charge le préréglage… »).

    On redemande donc à chaque paragraphe sa hauteur À SA LARGEUR
    D'ARRIVÉE, et on recommence tant que la largeur bouge encore -- deux
    tours suffisent en pratique, la borne est là pour ne jamais boucler.
    L'application, elle, se corrige d'elle-même : tout redimensionnement
    réel déclenche le même recalcul (`_WrapLabel.resizeEvent`)."""
    from PySide6 import QtWidgets as _W
    largeur = None
    for _ in range(6):
        inner.layout().activate()
        inner.adjustSize()
        app.processEvents()
        for lab in inner.findChildren(_W.QLabel):
            ajuste = getattr(lab, "_ajuster_hauteur", None)
            if ajuste is not None:
                ajuste()
        inner.layout().activate()
        app.processEvents()
        if inner.width() == largeur:
            break
        largeur = inner.width()


def _grab(tp, nom_classe):
    """Construit le panneau hors écran et rend son image entière."""
    from PySide6 import QtCore, QtWidgets
    import inspect
    cls = getattr(tp, nom_classe)
    params = list(inspect.signature(cls.__init__).parameters.items())[1:]
    besoin = [p for _n, p in params
              if p.default is inspect.Parameter.empty
              and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    p = cls([]) if besoin else cls()
    tp._auto_icon_buttons(p.form)
    w = p.form
    w.setFixedWidth(LARGEUR)
    w.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    w.resize(LARGEUR, HAUTEUR_MAX)
    w.show()
    app = QtWidgets.QApplication.instance()
    for _ in range(3):
        app.processEvents()
    inner = w.widget()
    if inner is not None and inner.layout() is not None:
        _stabiliser(app, inner)
    img = w.grab().toImage()
    fond = img.pixel(3, img.height() - 3)
    bas = min(_autocrop_bas(img, fond) + 6, img.height())
    return p, w, img, bas


def capturer(tp, nom_classe, hauteur, chemin_manuel, chemin_site):
    # Une seule construction, deux recadrages : la galerie prend le panneau
    # ENTIER (jusqu'à sa dernière rangée non vide), le manuel les premiers
    # `hauteur` pixels.
    _p, w, img, bas = _grab(tp, nom_classe)
    if bas >= HAUTEUR_MAX - 20:
        # Le recadrage a buté sur le plafond : ce panneau a un widget à
        # EXTENSION VERTICALE (grille de la Grille de test, règle de la Rampe)
        # qui s'étire jusqu'à la hauteur qu'on lui donne. Il n'y a pas de
        # « vraie » hauteur à trouver -- on s'en tient au recadrage du manuel
        # plutôt que de livrer une image de 3600 px étirée pour rien.
        bas = hauteur
    plein = img.copy(0, 0, LARGEUR, bas)
    plein.save(chemin_site)
    crop = img.copy(0, 0, LARGEUR, min(hauteur, bas))
    crop.save(chemin_manuel)
    w.deleteLater()
    return "{}x{} galerie / {}x{} manuel".format(
        plein.width(), plein.height(), crop.width(), crop.height())


def main(filtres):
    sys.path.insert(0, os.path.join(RACINE, "tests"))
    from harness import preparer
    h = preparer()
    tp = h.tp
    from PySide6 import QtWidgets
    # Un panneau qui ouvre une boîte de dialogue à l'instanciation bloquerait
    # la capture : on les neutralise toutes.
    for nom in ("warning", "information", "critical", "question", "about"):
        setattr(QtWidgets.QMessageBox, nom,
                staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok))
    for d in (IMG_MANUEL, IMG_SITE):
        if not os.path.isdir(d):
            os.makedirs(d)
    ok = rates = 0
    for nom, cls, hauteur, site in PANNEAUX:
        if filtres and not any(f.lower() in nom.lower() for f in filtres):
            continue
        cm = os.path.join(IMG_MANUEL, nom + ".png")
        cs = os.path.join(IMG_SITE, site + ".png")
        try:
            res = capturer(tp, cls, hauteur, cm, cs)
            print("  OK      {:<12} {}".format(nom, res))
            ok += 1
        except Exception as exc:
            print("  ÉCHEC   {:<12} {}".format(nom, repr(exc)[:110]))
            rates += 1
    print("\n{} capture(s) OK, {} échec(s)".format(ok, rates))
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
