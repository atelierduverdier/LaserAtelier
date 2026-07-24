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
    # Source principale : re-sélectionnée avec ses SOUS-ÉLÉMENTS si le job
    # en porte (plusieurs recettes sur un même sketch/SVG), entière sinon.
    principal = sources[0]
    sous = list(getattr(job, "SousElements", None) or [])
    if sous:
        for sub in sous:
            Gui.Selection.addSelection(principal, sub)
    else:
        Gui.Selection.addSelection(principal)
    for s in sources[1:]:
        Gui.Selection.addSelection(s)
    selection = Gui.Selection.getSelectionEx()
    import commands
    import task_panels
    panneau = getattr(task_panels, MODES[mode][2])
    commands._show(panneau(selection))
    FreeCAD.Console.PrintMessage(
        "Job « {} » rouvert (réglages de « {} »).\n".format(
            job.Label, sources[0].Label))


def _groupe_atelier(doc):
    """Le dossier « Atelier Laser » du document (créé au besoin) : il
    regroupe les Jobs et leurs formes sources pour garder l'arbre lisible."""
    for obj in doc.Objects:
        if getattr(obj, "Name", "") == "AtelierLaser" and hasattr(obj, "Group"):
            return obj
    grp = doc.addObject("App::DocumentObjectGroup", "AtelierLaser")
    grp.Label = "Atelier Laser"
    return grp


def _ranger_dans_groupe(doc, job, sources):
    """Range le Job -- et ses sources encore orphelines -- dans le dossier
    « Atelier Laser ». Une source déjà dans un groupe, un Body ou une Part
    n'est pas déplacée (on ne casse pas l'organisation de l'utilisateur)."""
    try:
        grp = _groupe_atelier(doc)
        contenu = list(getattr(grp, "Group", None) or [])
        if job not in contenu:
            grp.addObject(job)
        for src in sources:
            deja_range = (
                (getattr(src, "getParentGroup", lambda: None)() is not None)
                or (getattr(src, "getParentGeoFeatureGroup",
                            lambda: None)() is not None))
            if not deja_range and src not in contenu:
                grp.addObject(src)
                contenu.append(src)
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "Dossier « Atelier Laser » : rangement impossible ({}).\n".format(exc))


def ajouter_jobs_au_combine(jobs):
    """Empile les Jobs donnés (dans l'ordre) comme opérations du job
    combiné, chacun avec les réglages portés par sa forme : sélection des
    Jobs dans l'arbre + un bouton = le fichier unique, sans rouvrir chaque
    panneau. Renvoie (labels ajoutés, labels ignorés avec raison)."""
    import FreeCADGui as Gui
    import task_panels
    ajoutes, ignores = [], []
    for job in jobs:
        mode = getattr(job, "Mode", "")
        if mode not in MODES:
            ignores.append("{} (mode inconnu)".format(job.Label))
            continue
        panneau_cls = getattr(task_panels, MODES[mode][2])
        if not hasattr(panneau_cls, "_build_combined_operation"):
            ignores.append("{} (mode non combinable)".format(job.Label))
            continue
        sources = [o for o in (getattr(job, "Sources", None) or [])
                   if o is not None]
        if not sources:
            ignores.append("{} (forme source supprimée)".format(job.Label))
            continue
        # Même re-sélection que le double-clic : le panneau se pré-remplit
        # avec la recette de la forme, puis on capture son opération.
        Gui.Selection.clearSelection()
        principal = sources[0]
        sous = list(getattr(job, "SousElements", None) or [])
        if sous:
            for sub in sous:
                Gui.Selection.addSelection(principal, sub)
        else:
            Gui.Selection.addSelection(principal)
        for s in sources[1:]:
            Gui.Selection.addSelection(s)
        try:
            panneau = panneau_cls(Gui.Selection.getSelectionEx())
            op = panneau._build_combined_operation()
        except Exception as exc:
            ignores.append("{} ({})".format(job.Label, exc))
            continue
        if op is None:
            ignores.append("{} (opération invalide)".format(job.Label))
            continue
        op["label"] = job.Label
        # Idempotent : si une opération portant le Label de ce Job est déjà
        # dans le job combiné, on la REMPLACE (rafraîchit ses réglages) au
        # lieu d'empiler un doublon. Re-cliquer « Jobs -> combiné » ne gonfle
        # donc plus la liste -- sinon le G-code doublait de taille et l'aperçu
        # photo peignait chaque forme 2-3x (multiply) jusqu'au noir.
        existant = next((i for i, o in enumerate(task_panels._COMBINED_OPS)
                         if o.get("label") == job.Label), None)
        if existant is None:
            task_panels._COMBINED_OPS.append(op)
        else:
            task_panels._COMBINED_OPS[existant] = op
        ajoutes.append(job.Label)
    Gui.Selection.clearSelection()
    return ajoutes, ignores


def _est_job(obj):
    return getattr(obj, "Proxy", None).__class__.__name__ == "JobLaser" \
        if getattr(obj, "Proxy", None) is not None else False


def _poser_sources(obj, sources):
    """Pose (ou remplace) la propriété Sources du Job en portée GLOBALE
    (App::PropertyLinkListGlobal). Les formes gravées vivent souvent dans
    une App::Part alors que le Job est rangé dans le groupe « Atelier
    Laser » : un lien de portée LOCALE qui franchit cette frontière fait
    râler FreeCAD (« Link(s) ... go out of the allowed scope »). La portée
    globale l'autorise explicitement. Migre au passage les Jobs d'avant
    v1.9.3 (Sources en portée locale) en recréant la propriété."""
    a_migrer = True
    if hasattr(obj, "Sources"):
        try:
            a_migrer = obj.getTypeIdOfProperty("Sources") != "App::PropertyLinkListGlobal"
        except Exception:
            a_migrer = False  # pas de portée globale disponible : on garde tel quel
        if a_migrer:
            obj.removeProperty("Sources")
    if a_migrer:
        obj.addProperty("App::PropertyLinkListGlobal", "Sources", "Job",
                        "Formes sources du job (la première porte les réglages)")
    obj.Sources = sources


def creer_ou_maj_job(mode, sources, sous_elements=None):
    """Crée -- ou met à jour -- l'objet Job du triplet [mode, source
    principale, sous-éléments] dans le document actif. Appelé à chaque
    génération (task_panels._save_last_values). Deux sous-sélections
    différentes d'un même sketch/SVG donnent donc DEUX Jobs distincts,
    chacun avec sa recette. Renvoie le Job, ou None (pas de document,
    mode sans forme, sources invalides...)."""
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
    sous = sorted(sous_elements or [])

    # Job existant pour ce mode + cette source + ces sous-éléments :
    # mise à jour (les jobs d'avant la v1.5 n'ont pas SousElements --
    # getattr les traite comme « objet entier »).
    for obj in doc.Objects:
        if (_est_job(obj) and getattr(obj, "Mode", None) == mode
                and (getattr(obj, "Sources", None) or [None])[0] is principal
                and sorted(getattr(obj, "SousElements", None) or []) == sous):
            _poser_sources(obj, sources)
            _ranger_dans_groupe(doc, obj, sources)
            return obj

    obj = doc.addObject("App::FeaturePython",
                        "Job_{}_{}".format(mode, principal.Name))
    JobLaser(obj)
    obj.addProperty("App::PropertyString", "Mode", "Job",
                    "Mode de l'atelier laser (clé interne)")
    obj.Mode = mode
    obj.setEditorMode("Mode", 1)
    _poser_sources(obj, sources)
    obj.addProperty("App::PropertyStringList", "SousElements", "Job",
                    "Sous-éléments de la source principale (vide = objet entier)")
    obj.SousElements = sous
    obj.setEditorMode("SousElements", 1)
    obj.Label = "Job {} - {}{}".format(
        MODES[mode][0], principal.Label,
        " [" + ", ".join(sous) + "]" if sous else "")
    _ranger_dans_groupe(doc, obj, sources)
    if getattr(FreeCAD, "GuiUp", False) and getattr(obj, "ViewObject", None):
        VueJobLaser(obj.ViewObject)
    FreeCAD.Console.PrintMessage(
        "Job créé dans l'arborescence : « {} » (double-clic pour "
        "rouvrir le panneau pré-rempli).\n".format(obj.Label))
    return obj
