"""Classes de findings — la source unique des noms que le corpus oppose aux adaptateurs.

TF-0334, second volet. Le contrat de corpus (`recette/verifier_corpus.py`) apparie chaque
défaut planté à la CLASSE du finding qui le nomme (TF-0310). Ces classes étaient des
littéraux des deux côtés : une chaîne écrite à la main dans l adaptateur, la même chaîne
recopiée dans le corpus. Un renommage sortait donc l entrée en `[MANQUE]` — bruyant, donc
voulu, mais muet sur la CAUSE : rien ne distinguait « l adaptateur a cessé de détecter » de
« la classe s appelle autrement depuis hier ». Le diagnostic coûtait une bissection.

Le remède est celui de la loi 4 appliquée aux noms : une classe se DÉCLARE ici, s importe
partout ailleurs. Renommer devient l édition d une valeur, et le corpus suit sans être
touché ; ce qui reste rouge après un renommage est alors une vraie disparition de détection.

Les alias historiques (`interface.CLASSE_ECART_SERVI`, `qualif.CLASSE_ENTREE`…) restent
exposés par leurs modules : ils pointent désormais ici.
"""

from __future__ import annotations

# --- Couverture de surface (noyau) ---------------------------------------------------------
ELEMENT_NON_EXERCE = "element-non-exerce"
MODULE_NON_EXERCE = "module-non-exerce"
SEUIL_NON_TENU = "seuil-non-tenu"

# --- Mutation -------------------------------------------------------------------------------
MUTANT_SURVIVANT = "mutant-survivant"

# --- Confrontation code <-> déclaration -----------------------------------------------------
DIVERGENCE = "divergence"
SONDE_MUETTE = "sonde-muette"

# --- Interface statique ----------------------------------------------------------------------
AFFORDANCE_INERTE = "affordance-inerte"
LIEN_CASSE = "lien-casse"
ECART_SERVI_VERSIONNE = "ecart-servi-versionne"

# --- Instance servie (qualif) ------------------------------------------------------------------
ROUTE_EN_DEFAUT = "route-en-defaut"
AFFORDANCE_SANS_EFFET = "affordance-sans-effet"
REFUS_AUTORISATION = "acces-refuse-a-cette-identite"
CHAINE_AUTHENTIFICATION_EN_IMPASSE = "chaine-authentification-en-impasse"
URL_AUTO_REFERENTE_ETRANGERE = "url-auto-referente-etrangere"

# --- Pans spécialisés ---------------------------------------------------------------------------
SECURITE = "securite"
ACCESSIBILITE = "accessibilite"
REGRESSION_VISUELLE = "regression-visuelle"
MODELE_NON_EPINGLE = "modele-non-epingle"
I18N = "i18n"

# --- Déclencheurs de batch -----------------------------------------------------------------------
JOB_SANS_DECLENCHEUR = "job-sans-declencheur"
TRIGGER_NON_CABLE = "trigger-non-cable"
CRON_INVALIDE = "cron-invalide"

#: Toutes les classes déclarées — le verrou de TF-0334 s en sert dans les deux sens : aucune
#: classe du corpus hors de cet ensemble, aucun littéral de classe hors de ce module.
CLASSES: frozenset[str] = frozenset(
    valeur
    for nom, valeur in list(globals().items())
    if nom.isupper() and nom != "CLASSES" and isinstance(valeur, str)
)
