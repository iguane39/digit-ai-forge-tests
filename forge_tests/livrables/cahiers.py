"""Cahiers de tests DÉRIVÉS — jamais écrits à la main, et scellés pour que ça se voie.

Un cahier de tests rédigé à la main pourrit le jour de sa livraison : le produit bouge, le
cahier non, et personne ne sait plus quelle partie est encore vraie. Celui-ci est REGÉNÉRÉ à
chaque audit depuis le rapport. Ce n est pas un document, c est une vue.

**Définition opposable d « exhaustif »**, appliquée ici et vérifiée en recette :

    chaque élément de surface inventorié porte AU MOINS UN cas,
    OU figure en « non couvert » avec sa raison. Zéro absence silencieuse.

C est la seule définition qui se contrôle. « Tous les cas importants » ne se contrôle pas.

**Loi du générateur, héritée telle quelle** (voir `forge_tests.generateur`) : on ne produit
que ce qu on sait construire honnêtement. Un élément qu aucune exécution ne peut atteindre ici
(configuration absente) ne reçoit pas un cas de complaisance : il est déclaré NON COUVERT avec
les champs à fournir. Émettre un cas qu on sait injouable invite à l assouplir pour le faire
passer — le test-fitting que le garde-fou G-2 interdit.

**Séparation juge et partie.** Ces cahiers sont des PROPOSITIONS déposées dans un dossier
extérieur au projet (G-1). La forge n audite jamais des cas qu elle a produits et que le
produit n a pas adoptés : tant qu ils ne sont pas dans la suite du projet, ils ne comptent pour
rien dans la couverture mesurée.
"""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.livrables import exigences as _exigences
from forge_tests.livrables import jeux as _jeux
from forge_tests.livrables.nommage import empreinte, sceller

NON_JUGE = [
    "cahiers : un cas derive dit ce qu il faut VERIFIER, pas comment le produit l implemente — "
    "les etapes sont exprimees sur la surface (route, endpoint, contrainte), un scenario metier "
    "reste a ecrire par qui connait le metier",
    "cahiers : les etats vide, erreur et chargement sont des DEGRADATIONS generiques ; un ecran "
    "dont l etat vide a une semantique propre (premiere utilisation, filtre trop restrictif) "
    "reclame un cas supplementaire que la seule surface ne permet pas de deriver",
    "cahiers : l exhaustivite est verifiee sur les elements que le RAPPORT porte — un element "
    "qu aucun adaptateur n a su enumerer n est ni couvert ni declare non couvert, il est absent "
    "des deux, et c est la limite de l inventaire, pas celle du cahier",
    "cahiers : les gestes d un cas unitaire sont derives de la FORME de l identifiant "
    "(`code:METHODE /chemin=NNN`, `contrainte:x`, `mutant:...`) ; un identifiant de forme "
    "inconnue recoit un geste GENERIQUE, nomme comme tel dans le cas, a preciser par qui "
    "connait le pan",
]

_ETIQUETTE_ETAT = {
    "exerce": "exercé par la suite",
    "non_exerce": "inventorié, jamais exercé",
    "non_testable": "non testable ici (configuration absente)",
    "defaut": "défaut mesuré",
    "exclu": "exclu du périmètre, avec motif",
}


def _echapper(texte: object) -> str:
    """Une cellule de tableau Markdown ne survit pas à un `|` ni à un saut de ligne."""
    return str(texte or "").replace("|", "\\|").replace("\n", " ").strip()


# --- Dérivation des cas -----------------------------------------------------------------------
def _non_couvert(element: dict) -> str | None:
    """Raison pour laquelle cet élément ne reçoit PAS de cas — ou None s il en reçoit un."""
    if element["etat"] == "non_testable":
        champs = ", ".join(element.get("champs_requis") or []) or "la configuration manquante"
        return (
            f"aucune exécution ne pouvait l atteindre ici : fournir {champs}, puis `--reprendre` "
            "le rapport. Un cas écrit maintenant serait injouable"
        )
    if element["etat"] == "exclu":
        return f"exclu du périmètre par l adaptateur — {element.get('message') or 'sans motif'}"
    return None


_ROUTE_DANS_ID = re.compile(r"^(?:qualif:)?(?:route|a11y|visuel):(?P<route>/\S*)$")


def _ouverture(identifiant: str) -> str:
    """Premier geste d un cas d écran. Une route s ouvre ; un élément d écran se rejoint."""
    trouve = _ROUTE_DANS_ID.match(identifiant)
    if trouve:
        return f"ouvrir la route « {trouve['route']} » avec l acteur du jeu de données"
    return (
        f"ouvrir l écran du sous-chapitre avec l acteur du jeu de données, puis atteindre "
        f"« {identifiant} »"
    )


def _cas_etats(element: dict, chapitre: dict, cle_jeu: str) -> list[dict]:
    return [
        {
            "suffixe": etat,
            "titre": f"{element['id']} — état {etat}",
            "preconditions": _jeux._PRECONDITIONS[etat],
            "jeu": f"{cle_jeu} § {etat}",
            "etapes": [
                _ouverture(element["id"]),
                f"placer la dépendance dans l état « {etat} » selon les préconditions",
                "observer le rendu, la console et le code de réponse",
            ],
            "attendu": {
                "nominal": "l écran affiche les données du jeu ; aucune erreur console, aucun 5xx",
                "vide": "l écran affiche un état vide explicite (message ou zone dédiée), "
                "jamais une page blanche ni une erreur",
                "erreur": "l écran affiche un message d erreur lisible et reste utilisable ; "
                "aucune trace technique n est rendue à l utilisateur",
                "chargement": "l écran affiche un indicateur d attente ; aucune interaction "
                "destructrice n est possible pendant l attente",
            }[etat],
        }
        for etat in _jeux.ETATS_FONCTIONNELS
    ]


def _cas_rendu(element: dict, chapitre: dict, cle_jeu: str) -> list[dict]:
    rendu = chapitre.get("rendu") or {}
    themes = list(rendu.get("themes") or ("clair",))
    largeurs = list(rendu.get("largeurs_px") or (1280,))
    return [
        {
            "suffixe": f"{theme}-{largeur}",
            "titre": f"{element['id']} — golden thème {theme}, largeur {largeur} px",
            "preconditions": (
                f"golden accepté hors boucle pour ce couple (thème {theme}, {largeur} px) ; "
                "aucun golden n est créé pendant un run"
            ),
            "jeu": f"{cle_jeu} § nominal",
            "etapes": [
                f"servir la route et forcer le thème « {theme} »",
                f"capturer le rendu à {largeur} px de large",
                "comparer au golden accepté",
            ],
            "attendu": "aucune différence de rendu au-delà du seuil de l oracle ; toute "
            "différence est ARBITRÉE par un humain, jamais entérinée automatiquement",
        }
        for theme in themes
        for largeur in largeurs
    ]


def _cas_migration(element: dict, chapitre: dict, cle_jeu: str) -> list[dict]:
    sens = element["id"].rsplit(":", 1)[-1]
    libelle = {"up": "aller", "down": "retour"}.get(sens, sens)
    cas = [
        {
            "suffixe": libelle,
            "titre": f"{element['id']} — {libelle}",
            "preconditions": "base neuve, migrations antérieures appliquées dans l ordre",
            "jeu": f"{cle_jeu} § conforme",
            "etapes": [f"appliquer la migration au sens « {libelle} » sur une base neuve"],
            "attendu": "la migration s applique sans erreur et le schéma obtenu porte "
            "exactement les objets qu elle déclare",
        }
    ]
    if sens == "up":
        cas.append(
            {
                "suffixe": "rejeu",
                "titre": f"{element['id']} — rejeu (aller, retour, aller)",
                "preconditions": "base neuve, migrations antérieures appliquées",
                "jeu": f"{cle_jeu} § conforme",
                "etapes": ["appliquer l aller", "appliquer le retour", "réappliquer l aller"],
                "attendu": "le schéma final est identique au schéma obtenu par le premier "
                "aller : une migration non rejouable bloque tout retour arrière en production",
            }
        )
    return cas


# Un cas unitaire n a de sens que s il dit ce qu il faut FAIRE. « Exercer l élément avec la
# valeur conforme » convient à une contrainte de base, pas à un code de retour HTTP ni à un
# mutant survivant. Les gestes sont donc dérivés de la FORME de l identifiant — la seule chose
# que le rapport garantisse — et le repli générique est nommé comme tel dans le cahier.
_GESTES: tuple[tuple[re.Pattern[str], list[str], str], ...] = (
    (
        re.compile(r"^code:(?P<methode>[A-Z]+) (?P<chemin>\S+)=(?P<code>\d{3})$"),
        [
            "placer le système dans les conditions qui produisent le code {code} "
            "(jeu de données § conforme pour un succès, § violant pour un rejet)",
            "émettre {methode} {chemin}",
        ],
        "la réponse porte le code {code}, et une ASSERTION l affirme — un code observé sans "
        "assertion ne prouve rien",
    ),
    (
        re.compile(r"^endpoint:(?P<methode>[A-Z]+) (?P<chemin>\S+)$"),
        ["émettre {methode} {chemin} avec le jeu de données § conforme"],
        "la méthode est réellement atteinte et son résultat est affirmé, corps compris",
    ),
    (
        re.compile(r"^contrainte:(?P<nom>\S+)$"),
        [
            "insérer la ligne § conforme : elle doit être acceptée",
            "rejouer avec la valeur § violante, qui viole la contrainte {nom}",
        ],
        "le moteur REJETTE la seconde écriture et le test affirme le rejet — une contrainte "
        "jamais violée n est pas une contrainte vérifiée",
    ),
    (
        re.compile(r"^(?:table|index|trigger):(?P<nom>\S+)$"),
        [
            "écrire puis relire via {nom} avec le jeu § conforme",
            "vérifier que l objet est bien celui que la migration déclare",
        ],
        "l objet existe, il est utilisé par au moins un chemin de la suite, et son effet est "
        "affirmé",
    ),
    (
        re.compile(r"^mutant:(?P<module>[^:]+):(?P<ligne>\d+):(?P<mutation>.+)$"),
        [
            "appliquer la mutation « {mutation} » en ligne {ligne} de {module}",
            "rejouer la suite du projet",
        ],
        "au moins un test ÉCHOUE. S il passe, l assertion correspondante n affirme pas ce "
        "qu elle prétend : c est elle qu il faut renforcer, pas le mutant qu il faut retirer",
    ),
    (
        re.compile(r"^module(?:-non-exerce)?:(?P<module>\S+)$"),
        [
            "importer {module} depuis la suite",
            "exercer chacune de ses fonctions publiques avec le jeu § conforme puis § violant",
        ],
        "le module est chargé par au moins un test et son comportement est affirmé — un module "
        "jamais importé est du code dont personne ne sait s il fonctionne",
    ),
    (
        re.compile(r"^(?:branche|chemin):(?P<fichier>[^:]+):(?P<ligne>\d+)$"),
        [
            "construire l entrée qui emprunte la branche de la ligne {ligne} de {fichier} "
            "(§ violant pour un chemin d erreur, § conforme sinon)",
            "exécuter le traitement",
        ],
        "la branche est réellement parcourue et son effet propre est affirmé — un chemin "
        "d erreur non parcouru est une reprise qui échouera le jour où elle servira",
    ),
    (
        re.compile(r"^rejet:(?P<code>\S+)$"),
        ["provoquer le rejet {code} avec le jeu § violant"],
        "le traitement émet le code de rejet {code}, le journalise, et poursuit ou s arrête "
        "comme sa spécification le dit",
    ),
    (
        re.compile(r"^migration:(?P<fichier>[^:]+):(?P<sens>\w+)$"),
        ["appliquer la migration {fichier} au sens {sens} sur une base neuve"],
        "la migration s applique sans erreur et le schéma porte exactement ce qu elle déclare",
    ),
    (
        re.compile(r"^interface:(?P<fichier>[^:]+):(?P<ligne>\d+):(?P<balise>\w+)$"),
        [
            "ouvrir {fichier} et activer l affordance « {balise} » de la ligne {ligne}",
            "observer l effet produit",
        ],
        "l affordance produit un effet observable — une affordance est câblée, ou elle n existe "
        "pas",
    ),
    (
        re.compile(r"^securite:(?P<fichier>[^:]+):(?P<ligne>\d+)$"),
        [
            "relire {fichier} ligne {ligne}",
            "établir si l entrée traitée peut provenir d une source non maîtrisée",
        ],
        "le point signalé est soit supprimé, soit encadré par une validation, soit déclaré "
        "inoffensif AVEC son argument",
    ),
)

_GESTE_GENERIQUE = (
    ["exercer « {id} » avec le jeu § conforme", "rejouer avec le jeu § violant"],
    "la valeur conforme est acceptée, la valeur violante est REJETÉE, et le rejet est affirmé "
    "par une assertion",
)


def _cas_unitaire(element: dict, chapitre: dict, cle_jeu: str) -> list[dict]:
    identifiant = element["id"]
    for motif, etapes, attendu in _GESTES:
        trouve = motif.match(identifiant)
        if trouve:
            valeurs = {k: v or "" for k, v in trouve.groupdict().items()}
            gestes = [e.format(**valeurs) for e in etapes]
            resultat = attendu.format(**valeurs)
            generique = False
            break
    else:
        etapes, attendu = _GESTE_GENERIQUE
        gestes = [e.format(id=identifiant) for e in etapes]
        resultat = attendu
        generique = True
    return [
        {
            "suffixe": "verification",
            "titre": identifiant + (" — geste générique (forme non reconnue)" if generique else ""),
            "preconditions": "le jeu de données du sous-chapitre est chargé"
            + (
                " ; la FORME de cet identifiant n est pas reconnue par le cahier, les gestes "
                "ci-dessous sont un repli déclaré, à préciser par qui connaît le pan"
                if generique
                else ""
            ),
            "jeu": f"{cle_jeu} § conforme puis § violant",
            "etapes": gestes,
            "attendu": (
                f"{resultat}"
                + (f" (constat mesuré : {element['message']})" if element.get("message") else "")
            ),
        }
    ]


_FABRIQUES = {
    "etats": _cas_etats,
    "rendu": _cas_rendu,
    "migration": _cas_migration,
    "unitaire": _cas_unitaire,
}


def cas_du_chapitre(chapitre: dict, referentiel: dict | None) -> dict:
    """Cas et non-couverts d un chapitre. Chaque élément va dans l un ou dans l autre."""
    fabrique = _FABRIQUES.get(chapitre.get("axe_cas", "unitaire"), _cas_unitaire)
    repli = chapitre.get("axe_cas", "unitaire") not in _FABRIQUES
    sous_chapitres: list[dict] = []
    non_couverts: list[dict] = []
    rattachements: dict[str, list[dict]] = {}
    total_cas = 0
    for sous in chapitre["sous_chapitres"]:
        cle_jeu = f"JD-{chapitre['code']}-{sous['libelle']}"
        entrees = []
        for element in sous["elements"]:
            raison = _non_couvert(element)
            liens = _exigences.rattacher(referentiel, element)
            if raison:
                # Le rattachement n est PAS enregistré : une exigence touchée par le seul
                # élément qu on vient de déclarer non couvert serait comptée « couverte » à
                # l annexe. Ce serait exactement l inverse de ce que l annexe sert à montrer.
                non_couverts.append({**element, "raison": raison, "exigences": liens})
                continue
            rattachements[element["id"]] = liens
            cas = fabrique(element, chapitre, cle_jeu)
            for rang, unite in enumerate(cas, 1):
                # Référence STABLE : `hash()` est randomisé par processus en Python — deux
                # exécutions du même audit auraient produit deux cahiers différents, et le
                # sceau aurait accusé une édition manuelle qui n a jamais eu lieu.
                rang_stable = int(empreinte(element["id"])[:8], 16) % 9973
                unite["ref"] = f"{chapitre['code']}-{rang_stable:04d}-{rang}"
                unite["element"] = element["id"]
                unite["exigences"] = liens
            total_cas += len(cas)
            entrees.append({"element": element, "cas": cas})
        sous_chapitres.append({"libelle": sous["libelle"], "entrees": entrees, "cle_jeu": cle_jeu})
    return {
        **chapitre,
        "sous_chapitres": sous_chapitres,
        "non_couverts": non_couverts,
        "rattachements": rattachements,
        "total_cas": total_cas,
        "axe_repli": repli,
    }


# --- Rendu Markdown ---------------------------------------------------------------------------
def _rendre_exigences(liens: list[dict], referentiel: dict | None) -> str:
    if referentiel is None:
        return "_référentiel absent — cas dérivé de la seule surface_"
    if not liens:
        return "_aucune exigence rattachée (ni clé technique, ni rapprochement lexical)_"
    morceaux = []
    for lien in liens[:6]:
        if lien["provenance"] == "declare":
            morceaux.append(f"**{lien['id']}** (déclaré)")
        else:
            racines = ", ".join(lien.get("racines") or [])
            morceaux.append(f"{lien['id']} (lexical : {racines} — À VALIDER)")
    reste = f" … et {len(liens) - 6} autre(s)" if len(liens) > 6 else ""
    return ", ".join(morceaux) + reste


def _rendre_chapitre(chapitre: dict, referentiel: dict | None) -> list[str]:
    lignes = [f"## {chapitre['code']} — {chapitre['titre']}", ""]
    lignes.append(
        f"Pan(s) d origine : `{'`, `'.join(chapitre['pans'])}` · découpe par {chapitre['decoupe']} "
        f"· axe des cas : {chapitre.get('axe_cas')} · {chapitre['total_cas']} cas dérivés."
    )
    lignes.append("")
    if chapitre.get("axe_repli"):
        lignes.append(
            f"> Axe de cas « {chapitre.get('axe_cas')} » inconnu du générateur : repli sur des cas "
            "unitaires. Le repli est déclaré ici plutôt que silencieux."
        )
        lignes.append("")
    if not chapitre.get("axe_connu", True):
        lignes.append(
            f"> Axe de sous-chapitrage « {chapitre['decoupe']} » sans règle de rattachement : les "
            "éléments sont regroupés sous « non rattachés », nommément."
        )
        lignes.append("")
    if chapitre["grise"]:
        lignes.append(
            "> **Chapitre non mesuré.** Aucun élément n a pu être inventorié pour ce pan."
        )
        lignes.append("")
    for manquant in chapitre.get("pans_non_couverts") or []:
        lignes.append(
            f"> **Pan « {manquant.get('pan')} » NON COUVERT** — {manquant.get('motif')}  \n"
            f"> Pour couvrir : {manquant.get('pour_couvrir')}"
        )
        lignes.append("")

    # La numérotation porte sur les sous-chapitres RENDUS : un sous-chapitre dont tous les
    # éléments sont déclarés non couverts n en reçoit pas, et un trou dans la suite des numéros
    # ferait chercher au lecteur une section qui n existe pas.
    rang = 0
    for sous in chapitre["sous_chapitres"]:
        if not sous["entrees"]:
            continue
        rang += 1
        lignes.append(f"### {chapitre['code']}.{rang} — {sous['libelle']}")
        lignes.append("")
        lignes.append(f"Jeu de données : `{sous['cle_jeu']}`")
        lignes.append("")
        for entree in sous["entrees"]:
            element = entree["element"]
            lignes.append(
                f"#### `{element['id']}` — {_ETIQUETTE_ETAT.get(element['etat'], element['etat'])}"
            )
            lignes.append("")
            if element.get("message"):
                lignes.append(f"Constat mesuré : {element['message']}")
                lignes.append("")
            for unite in entree["cas"]:
                lignes.append(f"**{unite['ref']} — {unite['titre']}**")
                lignes.append("")
                lignes.append(f"- Préconditions : {unite['preconditions']}")
                lignes.append(f"- Jeu de données : `{unite['jeu']}`")
                liens = _rendre_exigences(unite["exigences"], referentiel)
                lignes.append(f"- Exigence(s) : {liens}")
                lignes.append("- Étapes :")
                for etape in unite["etapes"]:
                    lignes.append(f"  1. {etape}")
                lignes.append(f"- Résultat attendu : {unite['attendu']}")
                lignes.append("")

    if chapitre["non_couverts"]:
        lignes.append(f"### {chapitre['code']}.NC — éléments NON COUVERTS de ce chapitre")
        lignes.append("")
        lignes.append("| élément | état | raison |")
        lignes.append("| --- | --- | --- |")
        for element in chapitre["non_couverts"]:
            lignes.append(
                f"| `{_echapper(element['id'])}` | {_ETIQUETTE_ETAT.get(element['etat'], '')} "
                f"| {_echapper(element['raison'])} |"
            )
        lignes.append("")
    return lignes


def _entete(titre: str, contexte: dict, chapitres: list[dict]) -> list[str]:
    couverts = sum(c["total_cas"] for c in chapitres)
    # DISTINCTS : un même élément peut relever de deux chapitres (une route est à la fois un
    # parcours et un écran). Les additionner gonflerait l inventaire d un facteur sans aucun
    # sens, et le tableau d exhaustivité cesserait d être opposable.
    avec_cas = {
        entree["element"]["id"]
        for c in chapitres
        for sous in c["sous_chapitres"]
        for entree in sous["entrees"]
    }
    declares = {e["id"] for c in chapitres for e in c["non_couverts"]}
    non_couverts = len(declares)
    elements = len(avec_cas | declares)
    lignes = [
        f"# {titre}",
        "",
        f"Produit : **{contexte['produit']}** · audit du {contexte['date']} · "
        f"verdict du rapport : **{contexte['verdict']}**",
        "",
        "## Provenance — ce document est DÉRIVÉ, jamais rédigé",
        "",
        f"- rapport source : `{contexte['rapport_nom']}` "
        f"(sha256 `{contexte['rapport_sha'][:16]}…`)",
    ]
    if contexte["exigences_chemin"]:
        lignes.append(
            f"- référentiel d exigences : `{contexte['exigences_chemin']}` "
            f"(sha256 `{(contexte['exigences_sha'] or '')[:16]}…`) — "
            f"{contexte['exigences_nombre']} exigences lues"
        )
    else:
        lignes.append(
            "- référentiel d exigences : **ABSENT** — les cas sont dérivés de la SEULE SURFACE "
            f"inventoriée. Pour rattacher les cas aux exigences, déclarer "
            f"`{_exigences.VARIABLE}=<chemin EXIGENCES.json>`"
        )
    lignes += [
        f"- jeu de données associé : `{contexte['jeu_nom']}` — synthétique, vérifié avant écriture",
        "",
        "Ce cahier est régénéré à chaque audit. **Une édition manuelle est un défaut** : le sceau "
        "en tête la trahit, et la régénération suivante l écrase. Corriger la source, pas la vue.",
        "",
        "## Exhaustivité — définition opposable",
        "",
        "> Chaque élément de surface inventorié porte **au moins un cas**, ou figure en "
        "**« non couvert » avec sa raison**. Aucune absence silencieuse.",
        "",
        "| éléments inventoriés | cas dérivés | éléments non couverts (déclarés) |",
        "| --- | --- | --- |",
        f"| {elements} | {couverts} | {non_couverts} |",
        "",
        "Ces cas sont des **PROPOSITIONS** déposées hors du projet audité (garde-fou G-1). Tant "
        "que le produit ne les a pas adoptés, ils ne comptent pour rien dans la couverture "
        "mesurée : la forge n audite jamais ses propres cas.",
        "",
    ]
    return lignes


def _annexe_exigences(chapitres: list[dict], referentiel: dict | None) -> list[str]:
    if referentiel is None:
        return []
    rattachements: dict[str, list[dict]] = {}
    for chapitre in chapitres:
        rattachements.update(chapitre["rattachements"])
    orphelines = _exigences.sans_cas(referentiel, rattachements)
    lignes = [
        "## Annexe — couverture du référentiel d exigences",
        "",
        f"Référentiel : `{referentiel['chemin']}` · {len(referentiel['exigences'])} exigences · "
        f"{len(referentiel['exigences']) - len(orphelines)} touchée(s) par au moins un cas.",
        "",
        "Le rattachement d un cas à une exigence est **lexical** quand le référentiel ne porte "
        "pas de clé technique : il est publié avec sa provenance et doit être validé. Le "
        "présenter comme un fait fabriquerait une traçabilité fausse.",
        "",
    ]
    if orphelines:
        lignes += [
            "### Exigences qu AUCUN cas ne touche",
            "",
            "| exigence | palier | énoncé |",
            "| --- | --- | --- |",
        ]
        lignes += [
            f"| {e['id']} | {_echapper(e['palier'])} | {_echapper(e['enonce'])[:180]} |"
            for e in orphelines
        ]
        lignes.append("")
    else:
        lignes.append("Aucune exigence orpheline : toutes sont touchées par au moins un cas.")
        lignes.append("")
    return lignes


def construire(famille: str, titre: str, chapitres: list[dict], contexte: dict, referentiel) -> str:
    """Corps Markdown d un cahier — famille `fonctionnel` ou `technique`."""
    retenus = [c for c in chapitres if c["famille"] == famille]
    lignes = _entete(titre, contexte, retenus)
    for chapitre in retenus:
        lignes += _rendre_chapitre(chapitre, referentiel)
    if famille == "fonctionnel":
        lignes += _annexe_exigences(retenus, referentiel)
    lignes += [
        "## Dette de jugement de ce cahier",
        "",
        *[f"- {ligne}" for ligne in NON_JUGE],
        "",
    ]
    return "\n".join(lignes)


def ecrire(chemin: Path, corps: str, contexte: dict) -> Path:
    """Écrit le cahier scellé. Le sceau porte les sources ET l empreinte du corps."""
    entetes = {
        "produit": contexte["produit"],
        "genere_le": contexte["date"],
        "rapport_source": contexte["rapport_nom"],
        "rapport_sha256": contexte["rapport_sha"],
        "exigences_source": contexte["exigences_chemin"] or "(absent)",
        "exigences_sha256": contexte["exigences_sha"] or "(absent)",
        "jeu_de_donnees": contexte["jeu_nom"],
        "jeu_sha256": contexte.get("jeu_sha") or "(non encore écrit)",
    }
    texte = sceller(entetes, corps)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8", newline="\n")
    return chemin


def empreinte_du_corps(corps: str) -> str:
    return empreinte(corps)
