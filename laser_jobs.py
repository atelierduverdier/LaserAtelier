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

# COULEUR PAR MODE -- « le calque de LightBurn ». Christophe, 05/08/2026 :
# « il y a une sorte de calque pour chaque type de trait ou travail afin de
# les sélectionner ou pas pour la gravure, et aussi grâce à la couleur de
# voir sur l'écran quel job pour quel trait ».
#
# Les Jobs de l'arbre TENAIENT DÉJÀ le rôle de calques -- un par couple
# (mode, forme), avec l'icône du mode, et `ajouter_jobs_au_combine` en fait
# déjà un fichier unique. Il manquait la couleur et la case à cocher.
#
# Le rouge aux DEUX découpes (la coupe est ce qu'on ne rattrape pas), le
# bleu au marquage, le vert au remplissage, l'orange de la maison aux
# hachures. Deux nuances de rouge plutôt qu'une : à plat et sur relief ne
# se pilotent pas pareil, et les confondre coûte une pièce.
COULEURS_MODE = {
    "flat":       (0.85, 0.15, 0.15),      # découpe à plat -- rouge
    "curved_cut": (0.62, 0.09, 0.30),      # découpe courbe -- grenat
    "curved":     (0.13, 0.42, 0.78),      # marquage -- bleu
    "filled":     (0.16, 0.55, 0.28),      # gravure remplie -- vert
    "hatch":      (1.00, 0.54, 0.00),      # hachures -- l'orange de l'atelier
}

# CE QUI NOIRCIT UNE SURFACE se montre REMPLI ; ce qui marque ou coupe se
# montre au TRAIT. Christophe, 05/08/2026 : « pour les remplissages, il
# faudrait peut-être remplir la sélection d'une couleur et si on ne veut pas
# graver, ne pas remplir ; et pour le reste pareil, marquer d'une couleur
# sinon pas de marquage ».
#
# La couleur seule disait QUEL MODE ; elle dit maintenant QUEL TRAVAIL, ce
# qui est l'information qu'on cherche en regardant la planche. Gravure
# remplie et Hachures noircissent une aire -- on peint donc la face. Les
# deux découpes et le marquage suivent un trait -- on ne peint que le trait,
# et on laisse la face tranquille : forcer un solide 3D en fil de fer pour
# la beauté du calque rendrait le modèle inutilisable.
MODES_REMPLIS = {"filled", "hatch"}

# La couleur d'un job DÉCOCHÉ : un gris TRÈS clair, demandé tel quel (« ou
# alors un gris très clair pour les non gravés »). Assez pâle pour que la
# forme cesse de réclamer l'attention, assez visible pour qu'on la retrouve
# et qu'on la recoche. Un calque éteint doit se voir éteint, sinon la case
# ne sert qu'à celui qui se souvient de l'avoir mise.
GRIS_ETEINT = (0.85, 0.85, 0.85)


def _vue(obj):
    """Le ViewObject, ou None. `hasattr` est VRAI ET INUTILE en headless :
    l'attribut existe et vaut None, et la ligne suivante meurt sur
    None.LineColor. Le dépôt a déjà corrigé ce piège sur huit sites."""
    return getattr(obj, "ViewObject", None)


def _autres_jobs(doc, job, source):
    """Les autres Jobs qui visent la même forme, avec un mode différent."""
    out = []
    for o in doc.Objects:
        if o is job or not _est_job(o):
            continue
        if source in (getattr(o, "Sources", None) or []):
            if getattr(o, "Mode", None) != getattr(job, "Mode", None):
                out.append(o)
    return out


# QUI GAGNE QUAND PLUSIEURS JOBS SE PARTAGENT UNE FORME. Le premier de
# cette liste qui est COCHÉ donne sa couleur ; décocher un job fait donc
# apparaître celui d'en dessous, ce qu'on attend d'une pile de calques.
#
# LA v2.93 PEIGNAIT JOB PAR JOB, dernier arrivé gagnant -- si bien que
# décocher un job GRISAIT une forme que deux autres gravaient encore.
# Christophe, 05/08/2026, trois jobs sur un même texte : « quand je décoche
# gravure oui / non la couleur du dessous ou dessus ne s'affiche pas ». La
# couleur d'une forme partagée ne PEUT PAS se décider depuis un seul de ses
# jobs : il faut arbitrer sur l'ensemble.
#
# L'ordre suit la CONSÉQUENCE : ce qu'on ne rattrape pas d'abord.
PRIORITE_CALQUE = ("flat", "curved_cut", "filled", "hatch", "curved")


def rafraichir_calques(doc):
    """Repeint TOUTES les formes du document d'après TOUS les jobs.

    Renvoie {label de forme: [modes cochés]} pour les formes PARTAGÉES."""
    if doc is None:
        return {}
    par_forme = {}
    for o in doc.Objects:
        if not _est_job(o):
            continue
        mode = getattr(o, "Mode", "")
        if mode not in COULEURS_MODE:
            continue
        for src in (getattr(o, "Sources", None) or []):
            if src is not None:
                par_forme.setdefault(src, []).append(
                    (mode, bool(getattr(o, "Grave", True))))
    partagees = {}
    for src, jobs in par_forme.items():
        actifs = [m for m, g in jobs if g]
        if len(jobs) > 1:
            partagees[getattr(src, "Label", "?")] = actifs
        gagnant = next((m for m in PRIORITE_CALQUE if m in actifs), None)
        _peindre(src, gagnant)
    # Les surfaces d'aperçu suivent la case : on ne REBÂTIT pas ici (0,17 s
    # par texte), on ne fait que montrer ou cacher.
    for o in doc.Objects:
        if _est_job(o) and getattr(o, "Mode", "") in MODES_APERCU_PLEIN:
            _apercu_calque(o)
    return partagees


def _peindre(src, mode):
    """La couleur du mode sur la forme -- ou le gris d'extinction si `mode`
    est None (aucun job coché ne la vise)."""
    vue = _vue(src)
    if vue is None:
        return                            # headless : rien à peindre
    couleur = COULEURS_MODE[mode] if mode else GRIS_ETEINT
    remplit = bool(mode) and mode in MODES_REMPLIS
    for attr in ("LineColor", "PointColor", "ShapeColor"):
        if hasattr(vue, attr):
            try:
                setattr(vue, attr, couleur)
            except Exception:
                pass                      # une vue qui refuse n'arrête rien
    # UNE FORME SANS FACE NE SE REMPLIT PAS, et il faut le dire autrement.
    # Le « Texte gravé » de l'atelier est un compound de 1742 ARÊTES et
    # ZÉRO face : `ShapeColor` n'y peint rien, d'où « je ne vois pas de
    # remplissage ». Le TRAIT est la seule surface dont on dispose, donc un
    # job qui noircit une aire l'épaissit -- c'est ce qui distingue à l'oeil
    # « on remplit ça » de « on suit ce trait ».
    if hasattr(vue, "LineWidth"):
        try:
            vue.LineWidth = 4.0 if remplit else 2.0
        except Exception:
            pass
    if hasattr(vue, "Transparency"):
        try:
            vue.Transparency = 0 if mode else 70
        except Exception:
            pass


# LE CALQUE PLEIN : les modes dont l'aperçu vaut une VRAIE surface. Un
# contour n'a pas de face -- le « Texte gravé » de l'atelier est 1742 arêtes
# et zéro face -- mais la Gravure remplie sait déjà en BÂTIR pour calculer ce
# qu'elle va noircir. On montre donc cette surface-là.
#
# Christophe, 05/08/2026 : « je le veux car cela a vraiment un sens pratique
# et utile ». Mesuré sur son texte : 0,17 s pour 8 faces, 340 mm².
#
# LES HACHURES EN SONT EXCLUES EXPRÈS. Elles couvrent bien une aire, mais
# elles laissent du bois nu entre les traits : la peindre pleine promettrait
# un noir qu'elles ne rendent pas. La couleur et l'épaisseur du trait leur
# suffisent.
MODES_APERCU_PLEIN = ("filled",)

PROP_APERCU = "LaserAtelierApercuCalque"
TRANSPARENCE_APERCU = 35
# La surface se pose un cheveu SOUS le tracé : même Z, et le contour
# disparaît sous elle par moirage (z-fighting).
RECUL_APERCU_MM = 0.01


def _apercu_existant(doc, job):
    for o in doc.Objects:
        if getattr(o, PROP_APERCU, None) == job.Name:
            return o
    return None


def _apercu_calque(job, rebatir=False):
    """Pose (ou met à jour) la surface d'aperçu d'un job de remplissage.

    L'objet n'est JAMAIS une source de gravure : il est non sélectionnable
    dans la vue 3D, pour qu'un clic malheureux n'en fasse pas un motif."""
    doc = getattr(job, "Document", None)
    if doc is None or getattr(job, "Mode", "") not in MODES_APERCU_PLEIN:
        return None
    sources = [s for s in (getattr(job, "Sources", None) or []) if s is not None]
    if not sources:
        return None
    vieux = _apercu_existant(doc, job)
    if not rebatir:
        # RAFRAÎCHIR NE BÂTIT RIEN. Sans ce retour, un job dont la source ne
        # borne aucune surface -- une ligne ouverte, un motif non fermé --
        # retentait la construction des faces à CHAQUE clic sur la case, et
        # cette construction coûte 0,17 s sur un texte. Le test le compte :
        # il a trouvé quatre reconstructions pour deux bascules.
        if vieux is not None:
            _habiller_apercu(vieux, job)
        return vieux
    import laser_core as core
    faces = []
    for src in sources:
        forme = getattr(src, "Shape", None)
        if forme is None:
            continue
        if getattr(forme, "Faces", None):
            faces.extend(forme.Faces)          # déjà des faces : rien à bâtir
            continue
        try:
            baties = core._faces_from_any_shape(forme, getattr(src, "Label", "?"))
        except Exception:
            baties = None
        if baties:
            faces.extend(baties)
    if not faces:
        # Un contour OUVERT ne borne aucune surface : on le dit une fois
        # plutôt que de poser un objet vide que personne ne comprendrait.
        FreeCAD.Console.PrintWarning(
            "Aperçu de calque : « {} » ne délimite aucune surface fermée -- "
            "pas de remplissage à montrer.\n".format(job.Label))
        if vieux is not None:
            doc.removeObject(vieux.Name)
        return None
    import Part
    obj = vieux if vieux is not None else doc.addObject(
        "Part::Feature", "Calque_{}".format(job.Name))
    obj.Shape = Part.Compound(faces)
    plc = obj.Placement
    plc.Base.z = -RECUL_APERCU_MM
    obj.Placement = plc
    obj.Label = "Aperçu remplissage - {}".format(
        getattr(sources[0], "Label", "?"))
    if not hasattr(obj, PROP_APERCU):
        obj.addProperty("App::PropertyString", PROP_APERCU, "Job",
                        "Job dont cet objet montre la surface (aperçu, "
                        "jamais gravé)")
    setattr(obj, PROP_APERCU, job.Name)
    obj.setEditorMode(PROP_APERCU, 1)
    _habiller_apercu(obj, job)
    try:
        _groupe_atelier(doc).addObject(obj)
    except Exception:
        pass
    return obj


def _habiller_apercu(obj, job):
    """Couleur, transparence, visibilité -- et NON SÉLECTIONNABLE."""
    vue = _vue(obj)
    if vue is None:
        return
    grave = bool(getattr(job, "Grave", True))
    couleur = COULEURS_MODE.get(getattr(job, "Mode", ""), GRIS_ETEINT)
    for attr, val in (("ShapeColor", couleur), ("LineColor", couleur),
                      ("Transparency", TRANSPARENCE_APERCU),
                      ("Selectable", False), ("Visibility", grave)):
        if hasattr(vue, attr):
            try:
                setattr(vue, attr, val)
            except Exception:
                pass


def colorer_sources(job):
    """Repeint le document entier à partir de ce job. Gardée sous ce nom
    parce que les appelants en tiennent un, mais elle ARBITRE désormais sur
    l'ensemble. Renvoie les labels de SES formes qui sont partagées."""
    doc = getattr(job, "Document", None)
    if doc is None:
        return []
    partagees = rafraichir_calques(doc)
    miennes = {getattr(s, "Label", "?")
               for s in (getattr(job, "Sources", None) or []) if s is not None}
    return sorted(set(partagees) & miennes)

class JobLaser:
    """Proxy App::FeaturePython du Job : un signet, rien à recalculer."""

    def __init__(self, obj):
        obj.Proxy = self

    def execute(self, obj):
        pass

    def onChanged(self, obj, prop):
        """Décocher « Grave » doit se VOIR tout de suite, sinon la case ne
        sert qu'à celui qui se souvient de l'avoir mise."""
        if prop == "Grave":
            try:
                colorer_sources(obj)
            except Exception:
                pass          # une couleur ratée ne doit pas casser le doc

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

    def onDelete(self, vobj, _sub):
        """Supprimer le Job emporte sa surface d'aperçu -- sinon il resterait
        dans l'arbre un objet plein, coloré, sans rien pour l'expliquer."""
        try:
            job = vobj.Object
            doc = getattr(job, "Document", None)
            ap = _apercu_existant(doc, job) if doc is not None else None
            if ap is not None:
                doc.removeObject(ap.Name)
        except Exception:
            pass
        return True

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
        # DÉCOCHÉ = PAS GRAVÉ. `getattr` avec True par défaut : les Jobs
        # d'avant la v2.93 n'ont pas la propriété, et un ancien document
        # doit continuer à tout graver.
        if not bool(getattr(job, "Grave", True)):
            ignores.append("{} (décoché)".format(job.Label))
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


def _dire_disputees(job, labels):
    """Nomme les formes que DEUX jobs se disputent. On ne choisit pas à la
    place de l'utilisateur -- on lui dit ce que la couleur ne peut pas
    montrer."""
    if not labels:
        return
    FreeCAD.Console.PrintMessage(
        "Calques : « {} » sert à plusieurs jobs. La couleur montrée est "
        "celle du plus conséquent qui reste COCHÉ (ordre : {}) -- décoche-le "
        "et celui d'en dessous apparaît. Tous les jobs cochés sont gravés ; "
        "c'est l'affichage qui ne sait montrer qu'une couleur à la "
        "fois.\n".format(", ".join(labels),
                          " > ".join(MODES[m][0] for m in PRIORITE_CALQUE
                                     if m in MODES)))


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
            _apercu_calque(obj, rebatir=True)
            _dire_disputees(obj, colorer_sources(obj))
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
    # LA CASE À COCHER DU CALQUE. Sauvée avec le document, donc préparer une
    # planche une fois et n'en regraver qu'une partie ne demande plus de
    # re-sélectionner quoi que ce soit.
    obj.addProperty("App::PropertyBool", "Grave", "Job",
                    "Inclure ce job dans le job combiné (décoché : la forme "
                    "passe en gris et le job est ignoré)")
    obj.Grave = True
    obj.Label = "Job {} - {}{}".format(
        MODES[mode][0], principal.Label,
        " [" + ", ".join(sous) + "]" if sous else "")
    _ranger_dans_groupe(doc, obj, sources)
    if getattr(FreeCAD, "GuiUp", False) and getattr(obj, "ViewObject", None):
        VueJobLaser(obj.ViewObject)
    _apercu_calque(obj, rebatir=True)
    _dire_disputees(obj, colorer_sources(obj))
    FreeCAD.Console.PrintMessage(
        "Job créé dans l'arborescence : « {} » (double-clic pour "
        "rouvrir le panneau pré-rempli).\n".format(obj.Label))
    return obj
