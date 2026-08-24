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

import FreeCAD

import icones

# mode -> (libellé humain, icône, classe de panneau dans task_panels)
MODES = {
    "hatch":      ("Hachures",        "hatch.svg",      "TaskPanelHatch"),
    "filled":     ("Gravure remplie", "filled.svg",     "TaskPanelFilledEngraving"),
    "curved":     ("Marquage",        "curved.svg",     "TaskPanelCurved"),
    "flat":       ("Découpe à plat",  "flat.svg",       "TaskPanelFlat"),
    "curved_cut": ("Découpe courbe",  "curved_cut.svg", "TaskPanelCurvedCut"),
}

# LES MODES QUI FABRIQUENT UNE FORME, PAS DU G-CODE. Ils n'ont donc pas de
# Job : un Job est un signet vers une GÉNÉRATION, et ceux-là ne génèrent
# rien -- leur résultat est une forme, qu'on grave ensuite avec Marquage.
#
# Les Hachures étaient les seules à s'en créer un, et il ne pouvait rien
# faire : « mode non combinable » au job combiné, une case « Grave » sans
# objet, une couleur de calque sur une source qu'on ne grave pas. Christophe,
# 05/08/2026 : « je ne comprends pas le flux de travail [...] si ce n'est pas
# clair pour moi, cela ne le sera pas pour un nouvel utilisateur ». Il avait
# raison : Projection, Texte, Texte gravé et Calligraphie fabriquent aussi
# des formes et n'ont jamais créé de Job. Les Hachures étaient l'exception.
#
# On les GARDE dans MODES : les documents déjà créés ont des « Job Hachures »
# qu'il faut encore savoir nommer, iconifier et rouvrir.
MODES_GEOMETRIE = ("hatch",)


# COULEUR PAR MODE -- « le calque de LightBurn ». Christophe, 05/08/2026 :
# « il y a une sorte de calque pour chaque type de trait ou travail afin de
# les sélectionner ou pas pour la gravure, et aussi grâce à la couleur de
# voir sur l'écran quel job pour quel trait ».
#
# LES TEINTES VIENNENT DE LA ROUE DE L'ATELIER, celle qui teinte déjà les
# neuf barres d'outils (`laser_core.TEINTES_ATELIER`) -- une seule table,
# lue par les deux. Christophe : « il faudrait rester uni par rapport à la
# barre d'icônes et au reste ». Les couleurs d'origine étaient des primaires
# saturées qui juraient avec les barres pastel et les icônes orange-ardoise.
#
# CE QUE CE CHOIX COÛTE, ET IL A ÉTÉ MESURÉ : l'écart minimal entre deux
# calques tombe de 0,44 à 0,25. Rester dans la charte se paie en lisibilité,
# et c'est un arbitrage assumé, pas un oubli. Une variante plus stricte
# encore -- une teinte par BARRE, les deux modes d'une même barre séparés
# par la clarté -- descendait à 0,23 en mettant côte à côte deux clairs
# chauds (découpe courbe et hachures) : plus « uni » sur le papier, moins
# lisible sur l'écran, écartée pour ça.
#
# Chaque mode garde la teinte de SA barre quand elle est libre : rouge à la
# découpe à plat, orange de la maison à la gravure remplie, vert au
# marquage. Les deux qui se partageaient une barre empruntent une autre
# teinte de la même table plutôt qu'une nuance voisine indistinguable.
# L'indice de teinte de chaque mode dans la roue de l'atelier. Le TRAIT et
# la SURFACE y puisent la même, à deux tons différents -- une seule table,
# donc ils ne peuvent pas se retrouver de familles distinctes.
_TEINTE_INDICE = {
    "flat": 6,          # rouge -- sa propre barre
    "curved_cut": 7,    # magenta
    "filled": 4,        # orange -- sa barre ET la maison
    "hatch": 2,         # cyan
    "curved": 5,        # vert -- sa propre barre
}


def _couleurs_modes():
    import laser_core as core
    return {m: core.teinte_atelier(i) for m, i in _TEINTE_INDICE.items()}


class _CouleursModes(dict):
    """Le dictionnaire des couleurs, rempli à la PREMIÈRE lecture.

    `laser_jobs` est importé par FreeCAD au démarrage ; tirer `laser_core`
    à ce moment-là allongerait le lancement pour une couleur dont personne
    n'a encore besoin."""

    def _charger(self):
        if not dict.__len__(self):
            self.update(_couleurs_modes())

    def __getitem__(self, k):
        self._charger()
        return dict.__getitem__(self, k)

    def get(self, k, defaut=None):
        self._charger()
        return dict.get(self, k, defaut)

    def __contains__(self, k):
        self._charger()
        return dict.__contains__(self, k)

    def keys(self):
        self._charger()
        return dict.keys(self)

    def items(self):
        self._charger()
        return dict.items(self)

    def values(self):
        self._charger()
        return dict.values(self)

    def __len__(self):
        self._charger()
        return dict.__len__(self)

    def __iter__(self):
        self._charger()
        return dict.__iter__(self)


COULEURS_MODE = _CouleursModes()

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
        # LE TRAIT REVIENT AUX JOBS QUI SUIVENT UN TRAIT. Un remplissage
        # s'exprime par SA SURFACE (v2.95.0) ; lui laisser confisquer aussi
        # la couleur du contour revenait à rendre le marquage invisible dès
        # qu'un remplissage était coché. Christophe, 05/08/2026, un marquage
        # et un remplissage sur le même texte : « donc je ne verrai jamais
        # le vert sauf quand je cache l'aperçu ? ».
        #
        # Deux canaux, deux jobs : la surface dit ce qu'on noircit, le trait
        # dit ce qu'on parcourt. On les voit ENSEMBLE au lieu de l'un ou
        # l'autre.
        gagnant = next((m for m in PRIORITE_CALQUE
                        if m in actifs and m not in MODES_HORS_TRAIT), None)
        if gagnant is None:
            # Aucun job de trait : le remplissage ou les hachures reprennent
            # le contour, faute de quoi la forme paraîtrait éteinte alors
            # qu'elle sera bel et bien gravée.
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
    for attr in ("LineColor", "PointColor", "ShapeColor"):
        if hasattr(vue, attr):
            try:
                setattr(vue, attr, couleur)
            except Exception:
                pass                      # une vue qui refuse n'arrête rien
    # PAS DE LARGEUR DE TRAIT ICI, ET C'EST UN RETRAIT ASSUMÉ. La v2.94.1
    # épaississait le trait des modes remplissants, faute de savoir montrer
    # la surface : un pis-aller. La v2.95.0 pose la vraie surface, donc le
    # gros trait ne dit plus rien que l'aperçu ne dise mieux. Christophe :
    # « je pense que le bord large pour les remplis et autre on en a plus
    # besoin ». Élaguer plutôt qu'empiler -- et l'atelier cesse d'imposer
    # une largeur d'affichage qui ne le regarde pas.
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

# LES MODES QUI ONT LEUR PROPRE GÉOMÉTRIE ne prennent pas le contour de leur
# source. La v2.98.0 l'a fait pour le remplissage, qui a sa surface ; les
# HACHURES sont dans le même cas -- elles posent un objet « Hachures_… » bien
# à elles, visible tout seul. Les laisser confisquer le trait recréait le
# défaut un cran plus bas. Christophe, 05/08/2026 : « maintenant le fait de
# mettre des hachures enlève le contour vert ».
#
# Il reste donc au trait ce qui n'existe QUE comme parcours sur la forme :
# le marquage et les deux découpes.
MODES_HORS_TRAIT = ("filled", "hatch")

PROP_APERCU = "LaserAtelierApercuCalque"
TRANSPARENCE_APERCU = 35

# LA SURFACE EST UN TON PLUS CLAIR QUE LE TRAIT, même teinte. Christophe,
# 05/08/2026 : « le remplissage de couleur masque le contour du marquage ».
# Ce n'était pas la profondeur : sur son texte, la Gravure remplie gagne la
# priorité des calques, donc les TRAITS portaient déjà sa couleur -- et la
# surface posée dessous portait exactement la même. Le contour disparaissait
# dans son propre remplissage.
#
# Une aire et un chemin ne sont pas la même chose et ne doivent pas se
# peindre pareil. Même teinte pour rester dans la famille, valeur montée et
# saturation baissée pour que le trait se détache : écart mesuré 0,96 contre
# 0,00. C'est aussi la langue de la maison -- une famille, deux tons.
APERCU_SATURATION = 0.30
APERCU_VALEUR = 0.95

# La surface se pose un cheveu SOUS le tracé : à Z égal, le contour
# clignote sous elle (z-fighting). 0,05 mm plutôt que 0,01 : le tampon de
# profondeur d'une scène de 100 mm ne départage pas fiablement un centième,
# et cet objet n'est jamais gravé -- le recul ne coûte rien.
RECUL_APERCU_MM = 0.05


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
    faces, galbees = [], []
    for src in sources:
        forme = getattr(src, "Shape", None)
        if forme is None:
            continue
        if getattr(forme, "Faces", None):
            faces.extend(forme.Faces)          # déjà des faces : rien à bâtir
            continue
        # UNE FORME GALBÉE N'A PAS DE SURFACE PLANE À MONTRER. Sur un texte
        # projeté, le constructeur 2D rendait deux ou trois éclats -- le
        # point du i, la contreforme du e -- et l'aperçu mentait plus qu'il
        # n'informait. Le panneau, lui, refuse et dit le bon ordre.
        import laser_core as _c
        if not _c.forme_est_plane(forme):
            galbees.append(getattr(src, "Label", "?"))
            FreeCAD.Console.PrintWarning(
                "Aperçu de calque : « {} » n'est pas plat ({:.2f} mm de "
                "creux) -- la Gravure remplie travaille en 2D, il n'y a pas "
                "de surface à montrer.\n".format(
                    getattr(src, "Label", "?"), _c.ecart_au_plan(forme)))
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
        #
        # MAIS PAS DEUX FOIS POUR UNE SEULE CAUSE : quand toutes les sources
        # ont été écartées parce qu'elles sont galbées, on vient déjà de le
        # dire, et ce second message accuse à tort le contour d'être ouvert
        # -- en nommant le JOB, qui plus est. Vu tel quel dans la vue Rapport
        # de Christophe le 05/08/2026, juste sous le bon message.
        if not galbees:
            FreeCAD.Console.PrintWarning(
                "Aperçu de calque : « {} » ne délimite aucune surface "
                "fermée -- pas de remplissage à montrer.\n".format(job.Label))
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
        _ranger(doc, obj, "Apercus")
    except Exception:
        pass
    return obj


def _habiller_apercu(obj, job):
    """Couleur, transparence, visibilité -- et NON SÉLECTIONNABLE."""
    vue = _vue(obj)
    if vue is None:
        return
    import laser_core as core
    grave = bool(getattr(job, "Grave", True))
    mode = getattr(job, "Mode", "")
    couleur = _TEINTE_INDICE.get(mode)
    couleur = (core.teinte_atelier(couleur, APERCU_SATURATION, APERCU_VALEUR)
               if couleur is not None else GRIS_ETEINT)
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
        return icones.chemin(nom)

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


# TROIS RAYONS, PAS UN TAS. Christophe, 05/08/2026 : « peut-être faudrait-il
# ordonner un peu mieux les calques, d'un côté les jobs, de l'autre le
# compound que l'on a créé, et de l'autre les compounds qui se créent au fur
# et à mesure des ajouts de remplissage ou de marquage, sinon cela va être
# le foutoir ». Tout atterrissait à plat dans « Atelier Laser » ; sur son
# document, quatre objets de natures différentes s'y mêlaient déjà.
#
# Les trois natures ne se manipulent pas pareil : un JOB se coche et se
# double-clique, une FORME se sélectionne pour en faire un job, un APERÇU
# ne se touche jamais.
SOUS_GROUPES = (
    ("Jobs", "Jobs"),
    ("Formes", "Formes à graver"),
    # « Aperçus de remplissage » et non « Aperçus » : le rayon ne contient
    # QUE des surfaces de remplissage -- il n'existe pas d'aperçu de
    # marquage -- et un nom précis dit ce qu'on cache en cachant le dossier.
    # Christophe, 05/08/2026 : « comme cela on sait que l'on peut le cacher
    # si on ne veut pas voir les remplissages ». L'avertissement « ne pas
    # graver » qu'il portait n'a plus à tenir dans le libellé : depuis la
    # v2.96.0 c'est `_sans_apercus` qui l'empêche, à l'entrée des cinq modes.
    ("Apercus", "Aperçus de remplissage"),
)

# Nos anciens libellés : un dossier déjà posé garde son NOM interne, donc on
# le retrouve, mais son étiquette resterait celle d'avant. On la met à jour
# -- SEULEMENT si elle est encore l'une des nôtres, pour ne pas écraser un
# nom que l'utilisateur aurait choisi lui-même.
LIBELLES_ANCIENS = {"Apercus": ("Aperçus (ne pas graver)", "Aperçus")}


def _sous_groupe(doc, cle):
    """Le rayon `cle` de « Atelier Laser », créé au besoin."""
    grp = _groupe_atelier(doc)
    nom = "AtelierLaser{}".format(cle)
    voulu = dict(SOUS_GROUPES).get(cle, cle)
    for o in getattr(grp, "Group", None) or []:
        if getattr(o, "Name", "").startswith(nom):
            if getattr(o, "Label", "") in LIBELLES_ANCIENS.get(cle, ()):
                o.Label = voulu
            return o
    sous = doc.addObject("App::DocumentObjectGroup", nom)
    sous.Label = voulu
    grp.addObject(sous)
    return sous


def _ranger(doc, obj, cle):
    """Pose `obj` dans son rayon, en le retirant du rayon voisin s'il y
    traînait -- un objet rangé deux fois n'est rangé nulle part."""
    cible = _sous_groupe(doc, cle)
    if obj in (getattr(cible, "Group", None) or []):
        return
    grp = _groupe_atelier(doc)
    for autre in [grp] + list(getattr(grp, "Group", None) or []):
        if autre is cible or not hasattr(autre, "Group"):
            continue
        if obj in (getattr(autre, "Group", None) or []):
            autre.removeObject(obj)
    cible.addObject(obj)


def ranger_forme(obj):
    """Range une forme fabriquée par l'atelier dans « Formes à graver ».

    LES OBJETS QUE L'ATELIER CRÉE, C'EST À L'ATELIER DE LES RANGER. Jusqu'ici
    une forme n'atteignait son rayon qu'au moment où on lui faisait un JOB --
    or les Hachures n'en créent aucun (elles ne produisent que de la
    géométrie), si bien que leur objet restait à plat dans l'arbre, à côté du
    dossier plutôt que dedans. Christophe, 05/08/2026 : « le job
    hachures_paralleles n'est pas dans Aperçus de remplissage ».

    Ce n'est PAS un aperçu -- un aperçu ne se grave jamais, celui-ci est le
    tracé même que le laser suivra. Sa place est parmi les formes à graver.

    ON DÉPLACE, ON NE COPIE PAS -- et la question a été posée. Christophe,
    05/08/2026 : « ne vaudrait-il pas mieux faire une copie de la source dans
    Formes à graver et garder l'original là où il se trouve ? ». L'idée se
    tient pour l'arbre, et elle est refusée pour une raison de fond :

    UNE COPIE EST UNE SECONDE SOURCE DE VÉRITÉ. Rouvrir un texte ou une
    calligraphie reconstruit l'objet D'ORIGINE (`obj=repris`) ; la copie
    garderait l'ancien tracé, et le job pointant dessus graverait le texte
    périmé -- vu seulement sur le bois. C'est la famille exacte du job
    combiné qui gravait de vieux réglages (v2.99.9), de l'aperçu qui montrait
    une surface morte, et du Job qui devait rester un signet et non une
    deuxième vérité.

    Un App::Link éviterait la divergence, mais ajoute un objet par forme,
    affiche la géométrie deux fois et laisse indécis lequel des deux un job
    doit viser. Écarté aussi, après l'avoir posé sur la table.

    Et un groupe FreeCAD n'est qu'une organisation d'arbre : l'objet garde
    son nom, son placement et ses liens. Rien ne change pour la géométrie.

    Silencieuse : un rangement raté ne doit jamais empêcher de travailler."""
    try:
        doc = getattr(obj, "Document", None)
        if doc is None:
            return
        deja = (getattr(obj, "getParentGroup", lambda: None)()
                or getattr(obj, "getParentGeoFeatureGroup", lambda: None)())
        # Une forme que l'utilisateur a lui-même classée dans un Body ou une
        # Part ne bouge pas : on ne casse pas son organisation.
        if deja is not None and not getattr(
                deja, "Name", "").startswith("AtelierLaser"):
            return
        _ranger(doc, obj, "Formes")
    except Exception as exc:
        FreeCAD.Console.PrintLog(
            "Rangement de « {} » impossible ({}).\n".format(
                getattr(obj, "Label", "?"), exc))


def _ranger_dans_groupe(doc, job, sources):
    """Range le Job dans « Jobs », ses sources encore orphelines dans
    « Formes à graver », et l'aperçu du job dans « Aperçus ».

    Une source déjà dans un groupe, un Body ou une Part n'est PAS déplacée :
    on ne casse pas l'organisation de l'utilisateur."""
    try:
        _ranger(doc, job, "Jobs")
        for src in sources:
            deja_range = (
                (getattr(src, "getParentGroup", lambda: None)() is not None)
                or (getattr(src, "getParentGeoFeatureGroup",
                            lambda: None)() is not None))
            # `getParentGroup` répond « Atelier Laser » pour une forme qu'on
            # y a soi-même rangée : sans cette exception, une forme posée à
            # plat par une version précédente n'atteindrait jamais son rayon.
            parent = getattr(src, "getParentGroup", lambda: None)()
            a_nous = parent is not None and getattr(
                parent, "Name", "").startswith("AtelierLaser")
            if not deja_range or a_nous:
                _ranger(doc, src, "Formes")
        ap = _apercu_existant(doc, job)
        if ap is not None:
            _ranger(doc, ap, "Apercus")
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
        if mode in MODES_GEOMETRIE:
            # Un Job de ce genre ne peut venir que d'un document ancien : ce
            # mode fabrique une FORME, pas du G-code. Le dire, plutôt que de
            # laisser « mode non combinable », qui n'apprend rien.
            ignores.append(
                "{} — {} fabrique une FORME, pas du G-code : sélectionne la "
                "forme produite et grave-la avec Marquage de motif"
                .format(job.Label, MODES[mode][0]))
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
        # ON MÉMORISE LE JOB, pas seulement son nom. C'est ce qui permettra
        # de REPRENDRE ses réglages avant de graver : sans ce lien, une
        # opération est un instantané qui vieillit en silence.
        op["job"] = job.Name
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


def rafraichir_operations(ops, doc=None):
    """Reprend les réglages COURANTS de chaque opération issue d'un Job.

    UNE OPÉRATION EST UN INSTANTANÉ, et c'est le piège. `_build_combined_operation`
    capture les arêtes ET les réglages au moment de l'ajout ; modifier le job
    ensuite ne les touche pas. Christophe, 05/08/2026 : « j'ai changé un
    remplissage pour le mettre plus foncé, mais quand je vais dans les
    combinés, cela ne le prend pas en compte ». Il aurait gravé l'ANCIEN
    réglage -- une planche perdue, découverte sur le bois.

    Renvoie (labels repris, labels laissés tels quels avec la raison)."""
    import FreeCAD as _fc
    doc = doc or _fc.ActiveDocument
    if doc is None:
        return [], []
    par_nom = {o.Name: o for o in doc.Objects if _est_job(o)}
    repris, laisses = [], []
    for i, op in enumerate(list(ops)):
        nom = op.get("job")
        if not nom:
            laisses.append("{} (ajoutée depuis son mode, sans job)"
                           .format(op.get("label", "?")))
            continue
        job = par_nom.get(nom)
        if job is None:
            laisses.append("{} (son job a été supprimé)"
                           .format(op.get("label", "?")))
            continue
        avant = len(ops)
        ajoutes, ignores = ajouter_jobs_au_combine([job])
        if ajoutes:
            repris.append(job.Label)
        else:
            laisses.append(ignores[0] if ignores else job.Label)
        # `ajouter_jobs_au_combine` REMPLACE l'opération de même label : la
        # liste ne doit pas avoir grandi, sinon on empilerait des doublons.
        if len(ops) > avant:
            del ops[avant:]
            laisses.append("{} (remplacement impossible)".format(job.Label))
    return repris, laisses


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
    if mode not in MODES or mode in MODES_GEOMETRIE:
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
