# -*- coding: utf-8 -*-
"""laser_jobs.py -- objets « Job laser » de l'arborescence (niveau 2).
© Atelier du Verdier -- licence LGPL-2.1-or-later (cf. LICENSE).

Un Job est un signet visible dans l'arbre du document pour chaque
génération de G-code : il référence la ou les formes sources et le mode
utilisé. Les RÉGLAGES restent portés par la forme source (propriété
LaserAtelierReglages, cf. task_panels) : le Job n'est pas une seconde
source de vérité, c'est un point d'entrée.

Double-clic sur un Job : re-sélectionne ses sources et rouvre le panneau
du mode, pré-rempli avec les réglages de la forme -- modifier puis
régénérer, sans rechercher ni la forme ni les valeurs.

Un Job par couple [mode, source principale] : régénérer met à jour le
Job existant (sources), il ne s'en crée pas un nouveau à chaque fois.
Le Label reste modifiable par l'utilisateur (posé à la création
seulement)."""

import os
import FreeCAD

# mode -> (libellé humain, icône, classe de panneau dans task_panels)
MODES = {
    "hatch":      ("Hachures",        "hatch.svg",      "TaskPanelHatch"),
    "filled":     ("Gravure remplie", "filled.svg",     "TaskPanelFilledEngraving"),
    "curved":     ("Marquage",        "curved.svg",     "TaskPanelCurved"),
    "flat":       ("Découpe à plat",  "flat.svg",       "TaskPanelFlat"),
    "curved_cut": ("Découpe courbe",  "curved_cut.svg", "TaskPanelCurvedCut"),
}

_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "resources", "icons")


class JobLaser:
    """Proxy App::FeaturePython du Job : un signet, rien à recalculer."""

    def __init__(self, obj):
        obj.Proxy = self

    def execute(self, obj):
        pass

    # Sérialisation avec le document : le proxy ne porte aucun état
    # (tout est dans les propriétés de l'objet).
    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class VueJobLaser:
    """ViewProvider du Job : icône du mode + double-clic = rouvrir le
    panneau pré-rempli."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        mode = getattr(getattr(self, "Object", None), "Mode", "")
        nom = MODES.get(mode, (None, "workbench.svg", None))[1]
        return os.path.join(_ICON_DIR, nom)

    def doubleClicked(self, vobj):
        ouvrir_job(vobj.Object)
        return True  # on gère le double-clic : pas d'édition par défaut

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def ouvrir_job(job):
    """Re-sélectionne les sources du Job et rouvre le panneau de son mode,
    pré-rempli avec les réglages portés par la forme (niveau 1)."""
    mode = getattr(job, "Mode", "")
    if mode not in MODES:
        FreeCAD.Console.PrintWarning(
            "Job « {} » : mode inconnu ({}).\n".format(job.Label, mode))
        return
    sources = [o for o in (getattr(job, "Sources", None) or []) if o is not None]
    if not sources:
        FreeCAD.Console.PrintWarning(
            "Job « {} » : plus aucune source (forme supprimée ?) -- "
            "impossible de rouvrir le panneau.\n".format(job.Label))
        return
    import FreeCADGui as Gui
    Gui.Selection.clearSelection()
    for s in sources:
        Gui.Selection.addSelection(s)
    selection = Gui.Selection.getSelectionEx()
    import commands
    import task_panels
    panneau = getattr(task_panels, MODES[mode][2])
    commands._show(panneau(selection))
    FreeCAD.Console.PrintMessage(
        "Job « {} » rouvert (réglages de « {} »).\n".format(
            job.Label, sources[0].Label))


def _est_job(obj):
    return getattr(obj, "Proxy", None).__class__.__name__ == "JobLaser" \
        if getattr(obj, "Proxy", None) is not None else False


def creer_ou_maj_job(mode, sources):
    """Crée -- ou met à jour -- l'objet Job du couple [mode, source
    principale] dans le document actif. Appelé à chaque génération
    (task_panels._save_last_values). Renvoie le Job, ou None (pas de
    document, mode sans forme, sources invalides...)."""
    if mode not in MODES:
        return None
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None
    sources = [o for o in (sources or [])
               if o is not None and hasattr(o, "Document")]
    if not sources:
        return None
    principal = sources[0]

    # Job existant pour ce mode + cette source principale : mise à jour.
    for obj in doc.Objects:
        if (_est_job(obj) and getattr(obj, "Mode", None) == mode
                and (getattr(obj, "Sources", None) or [None])[0] is principal):
            obj.Sources = sources
            return obj

    obj = doc.addObject("App::FeaturePython",
                        "Job_{}_{}".format(mode, principal.Name))
    JobLaser(obj)
    obj.addProperty("App::PropertyString", "Mode", "Job",
                    "Mode de l'atelier laser (clé interne)")
    obj.Mode = mode
    obj.setEditorMode("Mode", 1)
    obj.addProperty("App::PropertyLinkList", "Sources", "Job",
                    "Formes sources du job (la première porte les réglages)")
    obj.Sources = sources
    obj.Label = "Job {} - {}".format(MODES[mode][0], principal.Label)
    if getattr(FreeCAD, "GuiUp", False) and getattr(obj, "ViewObject", None):
        VueJobLaser(obj.ViewObject)
    FreeCAD.Console.PrintMessage(
        "Job créé dans l'arborescence : « {} » (double-clic pour "
        "rouvrir le panneau pré-rempli).\n".format(obj.Label))
    return obj
