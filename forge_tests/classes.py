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
# TF-2269 : un test de la suite backend du projet est rouge. Distinct d'une couverture non mesurée
# (SKIP) : la cause est un test nommé, pas une absence de mesure.
SUITE_ROUGE = "suite-du-projet-rouge"
#: TF-1747 — une route servie et déclarée au schéma manque à l inventaire : défaut de l outil.
ENUMERATION_INCOMPLETE = "enumeration-incomplete"

# --- Interface statique ----------------------------------------------------------------------
AFFORDANCE_INERTE = "affordance-inerte"
LIEN_CASSE = "lien-casse"
ECART_SERVI_VERSIONNE = "ecart-servi-versionne"
# TF-0708 : un ecran de creation qui ne porte AUCUN des deux motifs legitimes. Classe distincte
# d `affordance-inerte` : ici les affordances sont cablees, c est la FORME de l ecran qui manque.
ECRAN_DE_CREATION_SANS_MOTIF = "ecran-de-creation-sans-motif"

# --- Instance servie (qualif) ------------------------------------------------------------------
ROUTE_EN_DEFAUT = "route-en-defaut"
AFFORDANCE_SANS_EFFET = "affordance-sans-effet"
REFUS_AUTORISATION = "acces-refuse-a-cette-identite"
CHAINE_AUTHENTIFICATION_EN_IMPASSE = "chaine-authentification-en-impasse"
URL_AUTO_REFERENTE_ETRANGERE = "url-auto-referente-etrangere"
# TF-1218 : un etat CLIENT rempli par l utilisateur qui ne survit pas a un aller-retour de
# navigation (panier vide apres ouverture de l aide), et un effet observe (une navigation) dont
# la destination trahit une attente DECLAREE pour l affordance qui l a produite.
ETAT_PERDU_A_LA_NAVIGATION = "etat-perdu-a-la-navigation"
DESTINATION_NON_PERTINENTE = "destination-non-pertinente"
# TF-1216 (instruction INS-0002 du 14/09/2026) : un couple identifiant / mot de passe affiche EN
# TEXTE dans une page SERVIE hors environnement local — ni le pan `interface` (cablage, jamais le
# texte rendu) ni forge-websec (corps de la reponse explicitement hors perimetre) ne le voyaient.
IDENTIFIANTS_AFFICHES = "identifiants-affiches-dans-le-texte-servi"
# TF-2525 : le même constat demande un second geste, de l'utilisateur — tenir le mot de passe
# affiché pour exposé et le renouveler (rotation). Le retirer de la page est le geste du
# développeur (`IDENTIFIANTS_AFFICHES`) ; une classe par destinataire, comme TF-2294.
IDENTIFIANTS_AFFICHES_A_RENOUVELER = "identifiants-affiches-a-renouveler"

# --- Pans spécialisés ---------------------------------------------------------------------------
SECURITE = "securite"
ACCESSIBILITE = "accessibilite"
REGRESSION_VISUELLE = "regression-visuelle"
MODELE_NON_EPINGLE = "modele-non-epingle"
# TF-2110 : un fichier de test qui appelle le fournisseur LLM réel (adresse ou client OpenAI /
# Gemini) sans aucun double — la suite dépense à chaque exécution.
APPEL_FOURNISSEUR_REEL_DANS_UN_TEST = "appel-fournisseur-llm-reel-dans-un-test"
I18N = "i18n"
# TF-1229 (volet a de TF-0964) : un fournisseur de jetons construit SANS l identifiant assigné,
# alors que l'environnement lu pose une identité assignée (`AZURE_CLIENT_ID`) — vu seulement en
# production jusqu'ici, aucun des trois oracles externes du pan `securite` ne le voit.
FOURNISSEUR_JETONS_SANS_IDENTIFIANT = "fournisseur-jetons-sans-identifiant"

# --- Revue statique de la suite de tests du projet (TF-0344 / TF-0345) --------------------------
FAUX_VERT_ABSENCE = "faux-vert-absence-sans-presence"
FAUX_VERT_MOTIF = "faux-vert-motif-du-declencheur"
DONNEE_DE_TEST_RECOPIEE = "donnee-de-test-recopiee"
FAUX_VERT_PREFIXE = "faux-vert-prefixe-d-un-chemin-valide"
TROU_DE_COUVERTURE_SOEUR = "trou-de-couverture-inter-suites"
# TF-0593 (retour Produit-01 du 24/08) : la session FABRIQUEE, et son corollaire de stockage.
SESSION_FABRIQUEE = "session-fabriquee-hors-parcours-d-entree"
SESSION_ET_CLE_SEPAREES = "cle-de-relecture-hors-du-stockage-de-la-session"

# --- Configuration de couverture : le chiffre avant la mesure (TF-0604) -------------------------
COUVERTURE_PERIMETRE_NON_DECLARE = "couverture-perimetre-non-declare"
COUVERTURE_SEUIL_GLOBAL_SEUL = "couverture-seuil-global-sans-seuil-par-fichier"
COUVERTURE_FONCTIONS_SANS_SEUIL = "couverture-fonctions-sans-seuil"

# --- Les tests qui ne s'executent pas, et que le reporting rend invisibles (TF-0605) ---------
SAUT_CONDITIONNEL = "saut-conditionnel-en-integration-continue"

# --- Un test qui passe sans avoir exécuté son assertion (TF-2216) --------------------------------
# Une boucle d'assertions sur une collection vide, ou une attente bornée dont l'expiration est
# avalée : le test est vert et n'a rien prouvé (Produit-86, 05/11 : 0 action approuvée).
ASSERTION_EXECUTEE_ZERO_FOIS = "assertion-de-test-executee-zero-fois"

# --- Un parcours qui juge l'état d'un traitement, jamais son résultat (TF-2270) ------------------
# Le test attend la fin d'un traitement (SUCCEEDED, « Terminé ») et s'arrête là : le traitement peut
# se terminer en rendant un résultat faux, vide ou périmé (Produit-86 : 34 parcours, 0 assertion sur
# le contenu d'un constat).
TRAITEMENT_SANS_RESULTAT_ASSERTE = "traitement-attendu-sans-resultat-assert"

# --- Réglages de plateforme exigés par le produit, lus en campagne (TF-2229) ----------------------
# Le réglage lu n'est pas celui que le registre des réglages sûrs attend (classement défaut), ou
# l'écart accepté par le porteur n'est pas tenu tel que décidé (classement décision).
REGLAGE_PLATEFORME_HORS_ATTENDU = "reglage-plateforme-hors-attendu"
REGLAGE_DECIDE_NON_TENU = "reglage-decide-non-tenu"

# --- Aller-retour écriture/relecture (TF-0369) ---------------------------------------------------
DEFAUT_EVALUE_A_L_IMPORT = "defaut-evalue-a-l-import"

# --- Surface appelée vs surface servie (TF-0371) -------------------------------------------------
ROUTE_APPELEE_NON_SERVIE = "route-appelee-non-servie"
RESSOURCE_REFERENCEE_ABSENTE = "ressource-referencee-absente"

# --- Matrice des droits et recette multi-profils (TF-0343 / TF-0342) ----------------------------
MATRICE_DES_DROITS = "matrice-des-droits"
# TF-2294 : un rôle déclaré sans session. Le geste est de l'utilisateur (fournir une identité par
# rôle), pas du développeur : une classe par destinataire, `matrice-des-droits` gardant les
# constats qui se ferment dans la suite du produit.
IDENTITES_DE_ROLES_MANQUANTES = "identites-de-roles-manquantes"

# --- Jeu du parcours d'un persona sous l'identité de son rôle (TF-2123) --------------------------
# Une route que le parcours du persona navigue est refusée à son rôle, renvoie vers la mire de
# connexion, ou répond en erreur sur l'instance servie. Distincte de `acces-refuse-a-cette-identite`
# (qualif, qui parcourt TOUTE l'application sous chaque rôle) : ici la route fait partie du parcours
# que le produit a écrit pour ce persona.
PARCOURS_PERSONA_REFUSE = "parcours-persona-refuse-sous-son-identite"

# --- Déclencheurs de batch -----------------------------------------------------------------------
JOB_SANS_DECLENCHEUR = "job-sans-declencheur"
TRIGGER_NON_CABLE = "trigger-non-cable"
CRON_INVALIDE = "cron-invalide"

# --- Supabase : RLS des tables exposées et migration Realtime (TF-2008) --------------------------
RLS_ABSENTE = "rls-absente"
REALTIME_RLS_REACTIVEE = "realtime-rls-reactivee"

#: Toutes les classes déclarées — le verrou de TF-0334 s en sert dans les deux sens : aucune
#: classe du corpus hors de cet ensemble, aucun littéral de classe hors de ce module.
CLASSES: frozenset[str] = frozenset(
    valeur
    for nom, valeur in list(globals().items())
    if nom.isupper() and nom != "CLASSES" and isinstance(valeur, str)
)
