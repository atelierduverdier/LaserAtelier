# -*- coding: utf-8 -*-
"""Harnais commun des tests headless de l'atelier.

Un test commence par `from harness import preparer` puis `h = preparer()`,
et travaille avec `h.core` / `h.tp`. Le harnais s'occupe de tout ce qui,
sinon, se recopie de test en test et finit par diverger :

- Qt en mode OFFSCREEN (aucune fenêtre ne s'ouvre).
- `FreeCADGui.Selection` bouchonné : plusieurs panneaux lisent la sélection
  3D à la construction, et elle n'existe pas sans interface graphique.
- **La config est redirigée vers une COPIE jetable.** C'est la règle la plus
  importante de ce dossier : un test ne doit JAMAIS écrire dans la config de
  l'atelier. Elle contient des mesures faites au pied à coulisse sur du bois
  -- des heures d'établi, irremplaçables par un calcul. La copie garde les
  mêmes données (donc les tests lisent le vrai nuancier, la vraie table de
  kerf), mais toute écriture part à la poubelle.

Le dossier de l'atelier est aussi redirigé, pour que les photos de résultat
écrites par un test n'atterrissent pas à côté du code.
"""
import atexit
import os
import re
import shutil
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def preparer(config_reelle=True):
    """Prépare l'environnement et renvoie un objet portant `core`, `tp` et
    les utilitaires. `config_reelle=False` part d'une config VIDE (utile
    pour tester les cas « aucun matériau mesuré »)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if RACINE not in sys.path:
        sys.path.insert(0, RACINE)

    import FreeCAD
    import FreeCADGui
    if not hasattr(FreeCADGui, "Selection"):
        # `addSelection` MANQUAIT, et son absence tenait tout un chemin
        # hors de portée : `laser_jobs.ajouter_jobs_au_combine` et
        # `ouvrir_job` re-sélectionnent les sources avant de bâtir leur
        # opération, si bien qu'aucun essai ne pouvait les traverser --
        # seuls leurs retours anticipés (« décoché », « mode inconnu »)
        # étaient éprouvés. Un bouchon incomplet ne se voit pas : il ne
        # rougit pas, il rend juste une partie du code inatteignable.
        FreeCADGui.Selection = types.SimpleNamespace(
            getSelectionEx=lambda *a, **k: [],
            getSelection=lambda *a, **k: [],
            addSelection=lambda *a, **k: None,
            removeSelection=lambda *a, **k: None,
            clearSelection=lambda *a, **k: None)

    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    import laser_core as core

    bac = tempfile.mkdtemp(prefix="laseratelier-tests-")
    atexit.register(shutil.rmtree, bac, ignore_errors=True)
    copie = os.path.join(bac, "laser_atelier_config.json")
    if config_reelle and os.path.exists(core.CONFIG_FILE):
        shutil.copy(core.CONFIG_FILE, copie)
    else:
        with open(copie, "w") as f:
            f.write("{}")
    core.CONFIG_FILE = copie
    core._WORKBENCH_DIR = bac

    # Le CANAL DE PUISSANCE part toujours de l'état connu : « S » direct.
    #
    # `laser_core` applique les réglages utilisateur à l'import, donc depuis la
    # VRAIE config -- avant que la redirection ci-dessus n'ait lieu. C'est sans
    # conséquence pour les données mesurées (nuancier, largeurs brûlées), que
    # les tests veulent justement lire. Mais « Puissance par M67 » change le
    # FORMAT du G-code émis : le jour où Christophe a coché la case dans ses
    # Préférences (30/07/2026), trois suites sont passées au rouge d'un coup,
    # à chercher des mots `S` qui n'existaient plus. Un test ne doit pas
    # dépendre d'une case cochée sur la machine.
    #
    # La ligne est tirée là, et pas ailleurs : on neutralise ce qui change la
    # FORME de la sortie, jamais un paramètre physique (l'accélération reste
    # celle de la machine -- un test qui juge une durée doit la juger sur la
    # vraie valeur).
    #
    # ATTENTION si tu te sers du harness pour FABRIQUER un fichier destiné à
    # la machine : ce forçage tient pour les tests, pas pour le bois. Un
    # G-code écrit ainsi part en S DIRECT alors que la PrintNC tourne en
    # M67, et il saccade à chaque changement de puissance -- entendu à
    # l'oreille le 01/08/2026 sur une planche témoin, jamais vu à l'écran.
    # Rappeler `core._apply_settings_config()` avant d'écrire un tel
    # fichier, pour retrouver les vrais réglages de l'atelier.
    canal_puissance(core, m67=False)

    import task_panels as tp
    return types.SimpleNamespace(core=core, tp=tp, app=app, bac=bac,
                                 FreeCAD=FreeCAD, FreeCADGui=FreeCADGui)


def canal_puissance(core, m67):
    """Bascule le canal de puissance : `M67` synchronisé, ou mot `S` direct.

    Les constantes de commande en découlent toutes -- les changer une par une
    dans un test, c'est en oublier une. `_apply_settings_config` fait le même
    travail depuis la config ; ceci le fait sans y toucher."""
    core.POWER_M67 = bool(m67)
    if m67:
        core.CMD_ARM = core._CMD_ARM_M67
        core.CMD_BEAM_ON = core._CMD_BEAM_ON_M67
        core.CMD_BEAM_OFF = core._CMD_BEAM_OFF_M67
        core.CMD_DISARM = core._CMD_DISARM_M67
    else:
        core.CMD_ARM = core._CMD_ARM_LINUXCNC
        core.CMD_BEAM_ON = core._CMD_BEAM_ON_S
        core.CMD_BEAM_OFF = core._CMD_BEAM_OFF_S
        core.CMD_DISARM = core._CMD_DISARM_S


def sans_dialogues():
    """Neutralise les boîtes modales et renvoie la liste de ce qu'elles
    auraient affiché : `[(genre, titre, texte), ...]`, remplie au fil du test.

    Indispensable dès qu'un test CLIQUE un bouton : `QMessageBox.information`
    attend un clic humain, et en mode offscreen elle attend simplement pour
    toujours. Un test qui appuie sur « Enregistrer les mesures » se fige sans
    afficher la moindre ligne (les prints sont encore dans le tampon) -- rien
    ne ressemble plus à une boucle infinie.

    La liste est renvoyée plutôt que les dialogues purement supprimés : ce
    qu'un panneau annonce à l'utilisateur fait partie de son comportement, et
    un test a le droit de le vérifier.

    **`QInputDialog` compte AUSSI**, et l'oubli a coûté un blocage de 316 s le
    02/08/2026 : seul `QMessageBox` était neutralisé, si bien qu'un
    `QInputDialog.getItem` (« quelle planche cette photo montre-t-elle ? »)
    figeait le test exactement de la même façon. Toute classe qui ouvre une
    modale doit passer par ici -- la règle n'est pas « QMessageBox », c'est
    « rien qui attende un humain »."""
    from PySide6 import QtWidgets
    appels = []

    def _faux(genre, retour):
        def _f(_parent, titre="", texte_="", *a, **k):
            appels.append((genre, titre, texte_))
            return retour
        return staticmethod(_f)

    QtWidgets.QMessageBox.information = _faux("info", QtWidgets.QMessageBox.Ok)
    QtWidgets.QMessageBox.warning = _faux("avertissement", QtWidgets.QMessageBox.Ok)
    QtWidgets.QMessageBox.critical = _faux("erreur", QtWidgets.QMessageBox.Ok)
    QtWidgets.QMessageBox.question = _faux("question", QtWidgets.QMessageBox.Yes)

    def _saisie(genre, defaut):
        """Répond la valeur PROPOSÉE par le panneau (1re entrée d'une liste,
        texte/nombre par défaut) plutôt qu'une valeur inventée : un test qui
        n'a rien à dire sur la saisie doit se comporter comme un utilisateur
        qui valide sans rien changer."""
        def _f(_parent, titre="", texte_="", *a, **k):
            appels.append((genre, titre, texte_))
            if a:
                if genre == "liste":
                    items = a[0] or [""]
                    i = a[1] if len(a) > 1 and isinstance(a[1], int) else 0
                    return (items[i] if 0 <= i < len(items) else items[0]), True
                return a[0], True
            return defaut, True
        return staticmethod(_f)

    QtWidgets.QInputDialog.getItem = _saisie("liste", "")
    QtWidgets.QInputDialog.getText = _saisie("texte", "")
    QtWidgets.QInputDialog.getDouble = _saisie("nombre", 0.0)
    QtWidgets.QInputDialog.getInt = _saisie("entier", 0)
    return appels


# --- Utilitaires partagés --------------------------------------------------

def texte(widget_ou_html):
    """Texte visible d'un QLabel : les verdicts sont écrits en HTML (gras,
    couleur), et un test qui chercherait « 0.30 mm » dans le balisage brut
    passerait à côté dès qu'on met un mot en gras."""
    s = widget_ou_html if isinstance(widget_ou_html, str) else widget_ou_html.text()
    return re.sub(r"<[^>]+>", "", s).strip()


def mouvements(gcode):
    """[(distance_mm, x, y, est_gravure), ...] de chaque déplacement."""
    import math
    x = y = None
    out = []
    for l in gcode.split("\n"):
        mx = re.search(r"\bX(-?\d+\.?\d*)", l)
        my = re.search(r"\bY(-?\d+\.?\d*)", l)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        if l.startswith(("G0 ", "G1 ")) and None not in (x, y, nx, ny):
            d = math.hypot(nx - x, ny - y)
            if d > 1e-9:
                out.append((d, nx, ny, l.startswith("G1 ")))
        x, y = nx, ny
    return out


def trajet_a_vide(gcode):
    """Longueur des déplacements faisceau éteint (mm)."""
    return sum(d for d, _x, _y, grave in mouvements(gcode) if not grave)


def demi_tours_x(gcode):
    """Nombre de CHANGEMENTS DE SENS en X à l'intérieur d'une même ligne
    (Y constant).

    Un tramage à points pose un micro-trait par case. S'il le grave
    toujours vers la droite, la machine doit RECULER avant chaque point des
    lignes parcourues vers la gauche : un aller-retour par point, des
    dizaines de milliers de fois. Rien dans le G-code ne le signale -- ni
    erreur, ni avertissement, et le résultat gravé est le même. Ce qui
    change, c'est ce qu'on entend à l'atelier. Il faut donc compter les
    inversions : sur une image balayée, la réponse attendue est ZÉRO.
    """
    n = 0
    x = y = sens = None
    for l in gcode.split("\n"):
        mx = re.search(r"\bX(-?\d+\.?\d*)", l)
        my = re.search(r"\bY(-?\d+\.?\d*)", l)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        if l.startswith(("G0 ", "G1 ")) and None not in (x, y, nx, ny):
            if abs(ny - y) > 1e-9:
                sens = None            # changement de ligne : on repart à zéro
            elif abs(nx - x) > 1e-9:
                s = 1 if nx > x else -1
                if sens is not None and s != sens:
                    n += 1
                sens = s
        x, y = nx, ny
    return n


def hauteurs_z(gcode):
    """Ensemble des Z rencontrés."""
    return {float(v) for v in re.findall(r"Z(-?\d+\.?\d*)", gcode)}


def puissances(gcode, gravure_seule=False):
    """Valeurs de S. `gravure_seule` : uniquement celles portées par un G1
    (les S0 de fin de ligne coupent le faisceau, ce n'est pas une gravure)."""
    if gravure_seule:
        return {int(m.group(1)) for m in
                (re.search(r"\bS(\d+)", l) for l in gcode.split("\n")
                 if l.startswith("G1 ")) if m}
    return {int(m) for m in re.findall(r"\bS(\d+)\b", gcode)}


def image_demo():
    """Une image réelle pour les tests photo, ou None si absente."""
    for p in ("/home/christophe/Images/Moi-laser/moi_gravure_contraste.png",
              os.path.join(RACINE, "resources", "demo", "photo_demo.jpg")):
        if os.path.exists(p):
            return p
    return None


# Table de largeurs brûlées de RÉFÉRENCE des tests.
#
# Le harnais travaille sur une COPIE de la config de l'atelier, ce qui est
# précieux : les tests lisent le vrai nuancier et la vraie table de kerf.
# Mais plusieurs d'entre eux avaient fini par encoder les valeurs du hêtre
# telles qu'elles étaient à un instant donné -- « au-delà de F800 le trait
# n'enfle plus », « la plus rapide vitesse utile est F800 ».
#
# Le 01/08/2026 Christophe a mesuré F1000 à F3000 sur une planche fraîche.
# `swell_max_feed` est passé de 800 à 3000 et QUATRE tests sont tombés d'un
# coup, sans qu'une ligne de code ait bougé. Un test qui rougit parce que
# l'utilisateur MESURE est pire qu'inutile : il apprend à ignorer le rouge,
# et c'est exactement ce qu'on lui demande de faire, mesurer.
#
# `figer_largeurs` réinstalle cette table connue DANS LA COPIE. À appeler
# dans tout test dont la propriété testée suppose une forme de table
# précise. Les tests qui vérifient que les données de l'atelier se tiennent
# doivent au contraire s'en abstenir.
LARGEURS_REFERENCE = {200.0: 0.10, 400.0: 0.15, 600.0: 0.20,
                      800.0: 0.25, 1000.0: 0.30}
FEEDS_ENFLE = (200.0, 400.0, 800.0)      # le trait enfle : 0,10 -> 0,30
FEEDS_PLATS = (1500.0, 3000.0)           # plat a 0,10 : plus rien a moduler


# Niveau de défocus -> diamètre du point OPTIQUE, tel que la calibration de
# l'atelier le donne. La brûlure reste TOUJOURS en dessous : au défocus les
# bords du faisceau n'atteignent plus le seuil de combustion. Les tests
# vérifient cette inégalité, donc la table de référence doit la respecter.
POINT_OPTIQUE_REF = {15.0: 1.16, 36.0: 2.36}
FEEDS_DEFOCUS_REF = (200.0, 400.0, 600.0, 800.0)


def figer_largeurs(core, materiau=u"Hêtre", defocus=True):
    """Remplace la table AU FOYER de ce matériau par LARGEURS_REFERENCE.

    Le défocus est conservé tel quel, ainsi que le nuancier : seule la
    grille du foyer est figée, c'est elle dont dépendent `burn_width_range`,
    `swell_max_feed` et le contraste des « Lignes gravées ». Renvoie le nom
    du matériau, pour écrire `MAT = figer_largeurs(core)`."""
    data = dict(core.load_burn_widths(materiau) or {})
    data["focus"] = (
        [{"power": s, "feed": f, "width": w}
         for f in FEEDS_ENFLE for s, w in LARGEURS_REFERENCE.items()]
        + [{"power": s, "feed": f, "width": 0.10}
           for f in FEEDS_PLATS for s in LARGEURS_REFERENCE])
    if defocus:
        # Table de DÉFOCUS de référence : croissante avec la hauteur, et
        # croissante avec la puissance. Ce sont les deux propriétés que les
        # tests supposent, et que les vraies mesures ne garantissent pas --
        # le 01/08/2026, le hêtre est ressorti à 3,35 mm à 55 mm de défocus
        # et 3,27 à 60, soit une DÉCROISSANCE (2,4 %, dans le bruit de
        # mesure). Un test qui suppose la monotonie doit se la donner.
        data["defocus"] = [
            {"power": s_, "feed": f_, "z_offset": z_,
             # 0,61 à 0,90 fois le point optique selon la puissance, moins
             # un peu quand ça va vite : croissant en z, croissant en S,
             # décroissant en F, et toujours SOUS le point optique.
             "width": round(pt * (0.54 + 0.00036 * s_) * (1.0 - f_ / 8000.0), 3)}
            for z_, pt in sorted(POINT_OPTIQUE_REF.items())
            for f_ in FEEDS_DEFOCUS_REF
            for s_ in LARGEURS_REFERENCE]
    core.save_burn_widths(materiau, data)
    return materiau
