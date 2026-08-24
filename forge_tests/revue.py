"""Revue statique de la suite de tests du projet — les faux verts, avant de les payer.

TF-0344 / TF-0345 (campagne du 17/08/2026), puis TF-0396, TF-0395 et TF-0578.

Un contre-oracle mesure ce que la suite ATTEINT et ce qu'elle VÉRIFIE. Aucun ne regardait la
suite elle-même **en tant que texte** — or trois faux verts sont tombés le même jour, sur la
même campagne, et aucun oracle ne les a vus. C'est cette moitié-là que ce module rend mécanique.
Le module a grandi par CAS RÉELS : huit règles à ce jour, sept mécanisées et une déclarée
non détectable ici. Chacune porte son fait fondateur et sa mesure — un contrôle dont personne
ne sait plus ce qu'il a coûté est le premier qu'une campagne pressée désactive.

**(1) Assertion d'ABSENCE sans preuve de PRÉSENCE.** `toHaveCount(0)` passe sur une page encore
en chargement : il n'y a rien parce que rien n'est encore là. Le test du passage de main
séquentiel était vert en isolation et rouge en exécution complète, pour cette seule raison.
*Règle : toute assertion d'absence est précédée d'une assertion de présence sur le même écran.*

**(2) MOTIF satisfait par le DÉCLENCHEUR.** `getByText(/Refused|Refus/i)` matche le bouton
« Refuse ». L'assertion « le refus est enregistré » passait donc AVANT toute décision, ce qui
supprimait la barrière de synchronisation entre profils : instabilité un run sur deux, 30 s de
timeout par occurrence. Après correction, la suite complète est passée de 3,6 min à 36 s, avec
trois passages verts consécutifs — et le même défaut dormait dans un spec antérieur, vert depuis
le 12/08. *Règle : aucun motif d'assertion ne doit pouvoir être satisfait par le déclencheur de
l'action qu'il vérifie.* C'est la plus rentable des trois, et la plus facile à voir : un motif
d'assertion qui est un préfixe du libellé cliqué dans le même test.

**(3) CELLULE MUTANTE sur objet PARTAGÉ.** Dans la matrice des droits, l'approbation réussie du
profil N faisait avancer le circuit et ouvrait le tour du profil N+1, qui rendait 201 au lieu de
409 — faux échec. *Règle : toute cellule dont le succès mute l'état exige un objet neuf.* Elle
n'est pas détectable ici (il faudrait savoir ce que « muter » veut dire chez le projet) : elle
est portée par le patron de matrice des droits (TF-0343), qui la rend structurelle plutôt que
vérifiée après coup. Ce module la DÉCLARE en non-jugé, il ne fait pas semblant de la voir.

**(4) DONNÉE DE TEST RECOPIÉE (TF-0345).** Le PNG de référence des parcours e2e — 3316
caractères de base64 — était recopié dans chaque spec. En le reprenant pour la suite
inter-profils, 80 caractères ont sauté : le fichier gardait sa signature PNG et une taille
plausible, mais le worker sortait « broken data stream » et l'envoi restait bloqué. Quatre tests
en timeout, pour une cause invisible à la lecture du diff — le symptôme (Send jamais activé)
pointait vers la chaîne de conversion, pas vers la donnée. *Règle : une donnée de test partagée
se RÉFÉRENCE (un module dédié, importé), elle ne se recopie pas ; et si elle est générée, elle
se VALIDE à la génération plutôt qu'on ne fasse confiance au littéral.*

**(5) PRÉFIXE dont l'extension est un chemin valide (TF-0396, lot cockpit-ia 20/08).** Le
parcours écrit le 19/08 POUR couvrir un défaut de déconnexion affirmait
`toContain("/.auth/logout")` — vert sur le comportement défectueux, `/.auth/logout` (déconnexion
du compte Microsoft entier) et `/.auth/logout/complete` (déconnexion de l'application seule)
partageant ce préfixe. Le défaut a été trouvé par un humain qui a cliqué, pas par le test écrit
pour lui. *Règle : dès qu'un parcours affirme un lien, une action ou une redirection par
`toContain`, le chemin affirmé ne doit pas être le préfixe d'un autre chemin valide du même
corpus de specs — la cible s'affirme EXACTE (égalité, ou ensemble énuméré).*

**(6) ASSERTION PRÉSENTE CHEZ LA SUITE SŒUR, ABSENTE ICI (TF-0395, même lot).** Quand une
famille de suites parallèles couvre les variantes d'un même comportement (les modes
d'authentification), chaque suite affirme ce que son auteur avait en tête — rien ne demande à
une suite ce que sa sœur affirmait. Mesuré : la bascule EasyAuth du 17/08 a produit 13 parcours
sans reprendre l'assertion de déconnexion que la suite sœur portait ; le bouton a disparu de
l'environnement déployé pendant TROIS JOURS sous 68 parcours verts. *Règle : un CHEMIN
APPLICATIF affirmé par une suite sœur (répertoire frère du même dossier de specs) et jamais
mentionné ici est signalé comme trou de couverture — signal nommé, jamais bloquant : deux
variantes peuvent différer LÉGITIMEMENT, mais l'écart se lit, il ne se découvre pas en
production.*

**(7) SESSION FABRIQUÉE, au lieu d'être JOUÉE (TF-0578, lot Approval2 20260824c).** Quand
l'authentification réelle est indisponible — un fournisseur d'entreprise dont on ne peut pas
obtenir N identités sans N comptes réels — la solution tentante est d'écrire la session
directement dans le stockage du navigateur. C'est rapide, ça marche tout de suite, et ça saute
LE SEUL MÉCANISME QUI AURAIT DÉTECTÉ L'ERREUR : le contrôle d'audience de la bibliothèque
cliente, qu'une session désérialisée ne rejoue jamais. Mesuré : audience sautée pour les 5
profils de recette, `client_id` faux survivant NEUF JOURS, trois fichiers portant trois valeurs
du même identifiant, cinq workflows inter-profils échouant au PREMIER passage réel (run 13894)
après n'avoir jamais été verts, une demi-journée de diagnostic. *Règle : dans une recette de
bout en bout, une session s'obtient par le PARCOURS D'ENTRÉE RÉEL du produit ; toute session
écrite directement dans un stockage est un défaut.* Deux niveaux, parce que les confondre
rendrait la règle bruyante donc contournable : valeur composée SUR PLACE = session fabriquée,
bloquant ; valeur issue d'un APPEL = plausiblement un vrai jeton injecté, signalé — c'est ce que
fait le harnais de cette forge elle-même, où l'audience est vérifiée par le serveur émetteur.

**(8) LA CLÉ DE RELECTURE HORS DU STOCKAGE DE LA SESSION (TF-0578, corollaire).** Le premier
correctif d'Approval2 avait remplacé la fabrication par une vraie connexion par profil — et
cassait quand même les cinq workflows : le choix de profil vivait dans `sessionStorage`, que le
`storageState` de Playwright NE SAUVEGARDE PAS. Perdu au rejeu, l'application retombait
SILENCIEUSEMENT sur son identité nominale. Ce défaut passait `tsc`, `eslint`, 137 tests
unitaires ET le harnais de connexion lui-même ; seule l'exécution réelle des cinq workflows l'a
montré. *Règle : la clé qui permet de RELIRE une session vit au même endroit que la session —
les séparer recrée la divergence qu'on corrige, sous une forme moins visible.*
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Finding
from forge_tests.risque import coter

PAN = "front"

#: Les fichiers relus. Les suites Python ne sont PAS revues ici : les trois faux verts mesurés
#: sont des idiomes de navigateur, et transposer leurs motifs à pytest sans cas réel
#: fabriquerait du bruit. L'écart est déclaré (loi 3), il n'est pas tu.
SUFFIXES_SPEC = (".spec.ts", ".spec.js", ".spec.tsx", ".spec.jsx", ".test.ts", ".test.tsx")

#: Un littéral en dessous de cette longueur n'est pas une « donnée de test » : c'est un libellé.
#: 200 caractères est le seuil au-dessus duquel une recopie ne se relit plus à l'œil — le cas
#: fondateur en portait 3316, et l'écart de 80 caractères y était invisible.
LONGUEUR_DONNEE = 200

#: Deux littéraux longs qui se ressemblent à ce point sont la même donnée, recopiée. En dessous,
#: ce sont deux données différentes qui partagent un encodage.
RESSEMBLANCE = 0.90

NON_JUGE = [
    "revue de suite : la CELLULE MUTANTE sur objet partage (TF-0344, piege 3) n est pas "
    "detectable statiquement — savoir qu une action MUTE l etat demande de connaitre le metier. "
    "Elle est tenue par le patron de matrice des droits (TF-0343), qui exige un objet neuf pour "
    "toute cellule dont le succes mute l etat",
    "revue de suite : seules les suites de NAVIGATEUR sont relues (.spec.ts et voisins) — les "
    "suites Python ne le sont pas, faute de cas reel sur leurs idiomes",
    "revue de suite : lecture TEXTUELLE, pas d analyse de flot — un motif construit a "
    "l execution (variable, gabarit) echappe a ces regles",
    "revue de suite (piege 7, session fabriquee) : la PROVENANCE reelle de la valeur ecrite. "
    "L oracle distingue une valeur composee SUR PLACE (litteral, objet serialise) d une valeur "
    "issue d un APPEL, et il ne peut pas savoir si cet appel touche le produit ou compose la "
    "session ailleurs. Le second cas est SIGNALE, jamais mis en echec — c est exactement ce que "
    "fait le harnais de cette forge (`forge_tests/authentification.py`), ou le jeton vient d une "
    "authentification reelle et son audience est verifiee par le serveur qui l a emis",
    "revue de suite (piege 7) : les cles de session sont une liste FERMEE de fragments. Une cle "
    "de session dont le nom n en porte aucun passe, et c est assume : un controle qui attraperait "
    "toute cle de stockage attraperait les preferences d affichage, et se ferait desactiver",
    "revue de suite (piege 9, saut conditionnel) : la LICEITE d un saut. L oracle distingue une "
    "forme CONDITIONNELLE d une forme inconditionnelle motivee ; il ne peut pas savoir si le "
    "prealable d un saut conditionnel est en realite garanti par le harnais — auquel cas le saut "
    "ne se declenchera jamais et le constat est excedentaire. Le declarer coute une ligne de "
    "reponse ; le taire coute des mois de tests ignores en silence",
    "revue de suite (piege 9) : les sauts construits a l EXECUTION (une variable qui porte la "
    "condition, un decorateur compose) echappent a la lecture ligne a ligne. C est la limite "
    "commune a tout ce module, et elle vaut ici comme ailleurs",
    "revue de suite (piege 8) : le rapprochement `storageState` / `sessionStorage` est fait sur "
    "le CORPUS, pas sur le flot — une recette qui persiste son etat dans un projet et ecrit le "
    "sessionStorage dans un autre serait signalee a tort. Le cas ne s est jamais presente, et "
    "l ecart est declare plutot que couvert par une heuristique de plus",
]

_TEST = re.compile(r"^\s*(?:test|it)(?:\.\w+)*\s*\(\s*[\"'`](?P<nom>[^\"'`]+)", re.MULTILINE)

# Les assertions d ABSENCE réellement rencontrées, et leurs proches immédiates.
_ABSENCE = re.compile(
    r"toHaveCount\(\s*0\s*\)|\.not\s*\.\s*to(?:BeVisible|BeAttached|BeInViewport|HaveText)\(",
)
# Les assertions de PRÉSENCE qui acquittent la règle : elles prouvent que l écran est bien rendu.
_PRESENCE = re.compile(
    r"(?<!not\.)\bto(?:BeVisible|BeAttached|HaveText|ContainText|HaveURL|HaveTitle)\("
    r"|toHaveCount\(\s*[1-9]"
    r"|waitFor(?:LoadState|Selector|URL|Response)?\(",
)

# Un libellé cliqué : `getBy…('X')` ou `getBy…({ name: 'X' })` suivi d un `.click()` dans la
# même expression. La grammaire reste volontairement étroite — mieux vaut manquer un cas que
# fabriquer un faux positif sur un contrôle né pour supprimer des faux verts.
_CLIC = re.compile(
    r"getBy(?:Role|Text|Label|TestId|Title|Placeholder)\("
    r"(?:[^()]*?name\s*:\s*)?[\"'`/](?P<libelle>[^\"'`/]{2,60})[\"'`/]?[^;]{0,200}?\.click\(",
    re.DOTALL,
)
# Un motif d assertion : le texte cherché dans un `expect(...)`.
_MOTIF_ASSERTION = re.compile(
    r"expect\([^;]{0,200}?getBy(?:Role|Text|Label|Title)\("
    r"(?:[^()]*?name\s*:\s*)?(?P<delim>[\"'`]|/)(?P<motif>[^\"'`/]{2,60})(?P=delim)",
    re.DOTALL,
)
_LITTERAL_LONG = re.compile(
    r"[\"'`]([A-Za-z0-9+/=_-]{" + str(LONGUEUR_DONNEE) + r",})[\"'`]"
)


def _specs(cible: Path) -> list[Path]:
    fichiers = [
        chemin
        for chemin in sorted(cible.rglob("*"))
        if chemin.is_file()
        and chemin.name.endswith(SUFFIXES_SPEC)
        and "node_modules" not in chemin.parts
    ]
    return fichiers


def _blocs_de_test(texte: str) -> list[tuple[str, str]]:
    """(nom du test, corps) — découpe par déclaration de test, sans parser le JavaScript."""
    debuts = list(_TEST.finditer(texte))
    blocs = []
    for rang, trouve in enumerate(debuts):
        fin = debuts[rang + 1].start() if rang + 1 < len(debuts) else len(texte)
        blocs.append((trouve.group("nom"), texte[trouve.end():fin]))
    return blocs


def _alternatives(motif: str) -> list[str]:
    """`Refused|Refus` → les deux : une seule alternative satisfaite suffit à faire un faux vert."""
    return [part.strip() for part in motif.split("|") if part.strip()]


def absence_sans_presence(cible: Path) -> list[Finding]:
    """Piège 1 — une assertion d'absence qu'aucune assertion de présence ne précède."""
    findings: list[Finding] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        for nom, corps in _blocs_de_test(fichier.read_text(encoding="utf-8", errors="replace")):
            absence = _ABSENCE.search(corps)
            if not absence:
                continue
            presence = _PRESENCE.search(corps)
            if presence is not None and presence.start() < absence.start():
                continue
            identifiant = f"revue:absence-sans-presence:{relatif}:{nom}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.FAUX_VERT_ABSENCE,
                    localisation=relatif,
                    message=(
                        f"« {nom} » affirme une ABSENCE (`{absence.group(0)}`) sans qu aucune "
                        "assertion de PRESENCE ne l ait precedee sur le meme ecran : sur une "
                        "page encore en chargement, il n y a rien parce que rien n est encore "
                        "la. Vert en isolation, rouge en execution complete — mesure le 17/08"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )
    return findings


def motif_satisfait_par_le_declencheur(cible: Path) -> list[Finding]:
    """Piège 2 — le plus rentable, et le seul entièrement mécanisable des trois.

    Un motif d'assertion qui est un PRÉFIXE du libellé cliqué dans le même test peut être
    satisfait par le déclencheur lui-même : l'assertion passe avant que l'action ait produit
    quoi que ce soit, et la barrière de synchronisation disparaît.
    """
    findings: list[Finding] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        for nom, corps in _blocs_de_test(fichier.read_text(encoding="utf-8", errors="replace")):
            cliques = [trouve.group("libelle").strip() for trouve in _CLIC.finditer(corps)]
            if not cliques:
                continue
            for trouve in _MOTIF_ASSERTION.finditer(corps):
                for motif in _alternatives(trouve.group("motif")):
                    collisions = [
                        libelle
                        for libelle in cliques
                        if libelle.lower().startswith(motif.lower())
                    ]
                    if not collisions:
                        continue
                    identifiant = f"revue:motif-du-declencheur:{relatif}:{nom}:{motif}"
                    findings.append(
                        Finding(
                            id=identifiant,
                            classe=classes.FAUX_VERT_MOTIF,
                            localisation=relatif,
                            message=(
                                f"« {nom} » : le motif d assertion « {motif} » est un prefixe du "
                                f"libelle CLIQUE « {collisions[0]} » — l assertion peut etre "
                                "satisfaite par le declencheur lui-meme, avant toute action. "
                                "Mesure : instabilite 1 run sur 2, 30 s de timeout par "
                                "occurrence, suite passee de 3,6 min a 36 s apres correction"
                            ),
                            risque=coter(PAN, identifiant, relatif),
                        )
                    )
                    break
    return findings


def donnees_recopiees(cible: Path) -> list[Finding]:
    """TF-0345 — une donnée de test partagée se référence ; elle ne se recopie pas.

    Deux constats, et le second est le plus coûteux : la copie IDENTIQUE (la cause) et la copie
    DÉRIVÉE (le symptôme — 80 caractères perdus, quatre tests en timeout, un diagnostic égaré
    vers la chaîne de conversion parce que le symptôme ne pointe pas vers la donnée).
    """
    litteraux: list[tuple[str, str]] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        litteraux.extend((relatif, trouve.group(1)) for trouve in _LITTERAL_LONG.finditer(texte))

    findings: list[Finding] = []
    vus: set[tuple[str, str]] = set()
    for rang, (fichier_a, valeur_a) in enumerate(litteraux):
        for fichier_b, valeur_b in litteraux[rang + 1:]:
            if fichier_a == fichier_b:
                continue
            paire = tuple(sorted((fichier_a, fichier_b)))
            if paire in vus:
                continue
            ratio = SequenceMatcher(None, valeur_a, valeur_b).quick_ratio()
            if ratio < RESSEMBLANCE:
                continue
            vus.add(paire)
            identique = valeur_a == valeur_b
            identifiant = f"revue:donnee-recopiee:{paire[0]}:{paire[1]}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.DONNEE_DE_TEST_RECOPIEE,
                    localisation=paire[0],
                    message=(
                        (
                            f"la meme donnee de test ({len(valeur_a)} caracteres) est RECOPIEE "
                            f"dans {paire[0]} et {paire[1]}"
                            if identique
                            else (
                                f"deux litteraux longs quasi identiques ({ratio:.0%}) entre "
                                f"{paire[0]} ({len(valeur_a)} car.) et {paire[1]} "
                                f"({len(valeur_b)} car.) : une recopie a DERIVE"
                            )
                        )
                        + " — une donnee de test partagee se REFERENCE (un module dedie, "
                        "importe) et se VALIDE a la generation. Cas fondateur : 80 caracteres "
                        "perdus dans la recopie d un PNG base64, quatre tests en timeout, et un "
                        "diagnostic egare vers la chaine de conversion"
                    ),
                    risque=coter(PAN, identifiant, paire[0]),
                )
            )
    return findings


#: Chemins d'application relevés dans un texte de spec : « /segment/segment », querystring
#: exclue. Le point est admis dans un segment (/.auth/logout est le cas fondateur).
_CHEMIN = re.compile(r"[\"'`](/[.\w][\w./-]{1,80})[\"'`]")
_TOCONTAIN = re.compile(r"toContain(?:Text)?\s*\(\s*[\"'`](/[.\w][\w./-]{1,80})[\"'`]")


def _chemins_du_corpus(specs: list[Path]) -> set[str]:
    chemins: set[str] = set()
    for fichier in specs:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        chemins.update(m.group(1) for m in _CHEMIN.finditer(texte))
    return chemins


def prefixe_d_un_chemin_valide(cible: Path) -> list[Finding]:
    """Piège 5 — `toContain` sur un chemin dont une extension est elle-même un chemin du corpus.

    L'extension est reconnue à la frontière de segment (`p` + `/`, `?` ou `#`) : « /foo » face à
    « /foobar » n'est pas signalé — deux chemins distincts, pas un préfixe piégeux.
    """
    specs = _specs(cible)
    corpus = _chemins_du_corpus(specs)
    findings: list[Finding] = []
    for fichier in specs:
        relatif = fichier.relative_to(cible).as_posix()
        for nom, corps in _blocs_de_test(fichier.read_text(encoding="utf-8", errors="replace")):
            for trouve in _TOCONTAIN.finditer(corps):
                chemin = trouve.group(1)
                extensions = sorted(
                    q for q in corpus
                    if q != chemin and q.startswith(chemin) and q[len(chemin)] in "/?#"
                )
                if not extensions:
                    continue
                identifiant = f"revue:prefixe-chemin:{relatif}:{nom}"
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.FAUX_VERT_PREFIXE,
                        localisation=relatif,
                        message=(
                            f"« {nom} » affirme `toContain(\"{chemin}\")` alors que le corpus "
                            f"des specs porte aussi {', '.join(f'`{q}`' for q in extensions[:3])}"
                            f"{' …' if len(extensions) > 3 else ''} — l assertion est VERTE sur "
                            "les deux comportements, le voulu et le defectueux. La cible "
                            "s affirme EXACTE (egalite, ou ensemble enumere) : mesure le 20/08, "
                            "/.auth/logout couvrait /.auth/logout/complete et le defaut a ete "
                            "trouve par un humain qui a clique"
                        ),
                        risque=coter(PAN, identifiant, relatif),
                    )
                )
    return findings


def trous_de_couverture_inter_suites(cible: Path) -> list[Finding]:
    """Piège 6 — un chemin applicatif affirmé par une suite SŒUR et jamais mentionné ici.

    La famille est DÉCOUVERTE : les répertoires frères d'un même dossier qui contiennent chacun
    des specs. Le signal est par MEMBRE (le répertoire qui n'en parle pas), nommé et non
    bloquant : deux variantes peuvent différer légitimement, mais l'écart se lit — il ne se
    découvre pas en production trois jours plus tard.
    """
    specs = _specs(cible)
    par_dossier: dict[Path, list[Path]] = {}
    for fichier in specs:
        par_dossier.setdefault(fichier.parent, []).append(fichier)
    par_parent: dict[Path, list[Path]] = {}
    for dossier in par_dossier:
        par_parent.setdefault(dossier.parent, []).append(dossier)

    findings: list[Finding] = []
    for _parent, freres in sorted(par_parent.items()):
        if len(freres) < 2:
            continue  # pas de famille : rien à confronter
        chemins_par_membre = {
            membre: _chemins_du_corpus(par_dossier[membre]) for membre in freres
        }
        textes_par_membre = {
            membre: " ".join(
                f.read_text(encoding="utf-8", errors="replace") for f in par_dossier[membre]
            )
            for membre in freres
        }
        for membre in sorted(freres):
            ailleurs: dict[str, str] = {}
            for soeur in freres:
                if soeur == membre:
                    continue
                for chemin in chemins_par_membre[soeur]:
                    # Jamais MENTIONNÉ ici — même pas en texte libre : une simple mention vaut
                    # choix conscient, l absence totale vaut angle mort.
                    if chemin not in textes_par_membre[membre]:
                        ailleurs.setdefault(chemin, soeur.name)
            if not ailleurs:
                continue
            relatif = membre.relative_to(cible).as_posix()
            manquants = sorted(ailleurs)
            identifiant = f"revue:trou-inter-suites:{relatif}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.TROU_DE_COUVERTURE_SOEUR,
                    localisation=relatif,
                    severite="signale",
                    message=(
                        f"la suite `{relatif}` ne mentionne jamais {len(manquants)} chemin(s) "
                        "que ses suites sœurs affirment : "
                        + " · ".join(
                            f"`{c}` (chez {ailleurs[c]})" for c in manquants[:5]
                        )
                        + (f" (+{len(manquants) - 5} autres)" if len(manquants) > 5 else "")
                        + " — trou de couverture SIGNALÉ, pas un échec : deux variantes peuvent "
                        "différer légitimement, mais l écart se lit. Mesuré le 20/08 : la "
                        "bascule EasyAuth a perdu l assertion de déconnexion de sa sœur, trois "
                        "jours de production sous 68 parcours verts"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )
    return findings


#: TF-0578 (retour Approval2 du 24/08) — piège (7), LA SESSION FABRIQUÉE.
#:
#: Quand l'authentification réelle est indisponible — un fournisseur d'entreprise, Entra ID,
#: Google Workspace, Okta, dont on ne peut pas obtenir N identités sans N comptes réels — la
#: solution tentante est d'écrire la session DIRECTEMENT dans le stockage du navigateur : une
#: clé calculée à la main, la redirection sautée. C'est rapide, ça marche tout de suite, et ça
#: saute LE SEUL MÉCANISME QUI AURAIT DÉTECTÉ L'ERREUR — le contrôle d'audience de la
#: bibliothèque cliente, qu'une session désérialisée ne rejoue jamais.
#:
#: MESURÉ : contrôle d'audience sauté pour les 5 profils de recette · un `client_id` FAUX
#: survivant NEUF JOURS (12/08 au 21/08) · trois fichiers portant trois valeurs du même
#: identifiant, deux fausses · les 5 workflows inter-profils échouant au PREMIER passage réel
#: en intégration continue (run 13894) après n'avoir jamais été verts, ni à leur écriture ni
#: depuis · une demi-journée de diagnostic.
#:
#: DEUX NIVEAUX, et les confondre rendrait la règle bruyante — donc contournable (R-33 bis).
#: Une valeur COMPOSÉE SUR PLACE (littéral, objet littéral passé à `JSON.stringify`) est une
#: session fabriquée : bloquant. Une valeur qui vient d'un APPEL est plausiblement un vrai
#: jeton obtenu du produit puis injecté — c'est ce que fait le harnais de cette forge
#: elle-même (`forge_tests/authentification.py`), où l'audience est vérifiée par le serveur qui
#: l'a émis. Ce cas est SIGNALÉ, pas mis en échec : l'écart se lit, il ne s'accuse pas.
_STOCKAGE_ECRITURE = re.compile(
    r'(?P<stockage>localStorage|sessionStorage)\s*\.\s*setItem\s*\(\s*'
    r'["\'`](?P<cle>[^"\'`]{1,80})["\'`]\s*,\s*(?P<valeur>[^;]{0,200})',
    re.DOTALL,
)
#: Un cookie de session posé par le harnais plutôt que par le parcours : même geste, autre porte.
_COOKIE_POSE = re.compile(
    r'addCookies\s*\(\s*\[?[^;]{0,200}?name\s*:\s*["\'`](?P<cle>[^"\'`]{1,80})["\'`]',
    re.DOTALL,
)
#: Les fragments de clé qui désignent une session. Liste FERMÉE, même construction que les
#: termes ambigus de la conception : une clé de préférence d'affichage n'est pas une session, et
#: un contrôle qui les confond se fait contourner au lieu de se corriger.
_CLES_DE_SESSION = (
    "token", "session", "auth", "jwt", "bearer", "credential", "identity", "identite",
    "msal", "oidc", "oauth", "account", "compte", "login", "connexion", "profil", "profile",
    "user", "utilisateur", "claims", "principal",
)
#: Une valeur COMPOSÉE sur place : un littéral nu, ou l'objet/tableau littéral lui-même.
#: `JSON.stringify(…)` est retiré AVANT ce test — c'est le cas fondateur, et le compter comme un
#: appel classerait la session la plus manifestement inventée du lot parmi les jetons obtenus.
_VALEUR_COMPOSEE = re.compile(r'^\s*(?:["\'`]|[{\[])')
#: L'enveloppe de sérialisation, retirée pour lire ce qu'elle sérialise.
_SERIALISATION = re.compile(r'^\s*JSON\s*\.\s*(?:stringify)\s*\(')
#: Une valeur qui vient d'un APPEL — donc potentiellement du produit lui-même.
_VALEUR_OBTENUE = re.compile(r"\bawait\b|\w\s*\(")


def _valeur_composee_sur_place(valeur: str) -> bool:
    """Vrai si la valeur écrite est fabriquée ICI, faux si elle vient d'un appel.

    L'enveloppe `JSON.stringify(` est retirée d'abord : ce qui compte est ce qu'elle sérialise.
    Un objet littéral reste une session inventée ; un objet qui contient un appel ne l'est pas.
    """
    nue = _SERIALISATION.sub("", valeur, count=1).strip()
    return bool(_VALEUR_COMPOSEE.match(nue)) and not _VALEUR_OBTENUE.search(nue)


def _cle_de_session(cle: str) -> str | None:
    plie = cle.lower()
    for fragment in _CLES_DE_SESSION:
        if fragment in plie:
            return fragment
    return None


def session_fabriquee(cible: Path) -> list[Finding]:
    """Piège 7 — une session écrite dans un stockage au lieu d'être JOUÉE par le parcours réel.

    *Règle : dans une recette de bout en bout, une session s'obtient par le parcours d'entrée
    réel du produit ; toute session écrite directement dans un stockage est un défaut.*
    """
    findings: list[Finding] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for nom, corps in _blocs_de_test(texte) or [("(hors bloc de test)", texte)]:
            for trouve in _STOCKAGE_ECRITURE.finditer(corps):
                fragment = _cle_de_session(trouve.group("cle"))
                if fragment is None:
                    continue
                valeur = trouve.group("valeur").strip()
                composee = _valeur_composee_sur_place(valeur)
                identifiant = (
                    f"revue:session-fabriquee:{relatif}:{nom}:{trouve.group('cle')}"
                )
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.SESSION_FABRIQUEE,
                        localisation=relatif,
                        severite="bloquant" if composee else "signale",
                        message=(
                            f"« {nom} » ecrit la cle « {trouve.group('cle')} » "
                            f"(fragment de session « {fragment} ») DIRECTEMENT dans "
                            f"{trouve.group('stockage')}"
                            + (
                                " avec une valeur COMPOSEE SUR PLACE : c est une session "
                                "FABRIQUEE, et une session deserialisee ne rejoue jamais le "
                                "controle d audience de la bibliotheque cliente. Une session "
                                "s obtient par le PARCOURS D ENTREE REEL du produit. Mesure "
                                "le 24/08 : client_id faux survivant neuf jours, cinq "
                                "workflows inter-profils jamais verts, echec au premier "
                                "passage reel (run 13894), demi-journee de diagnostic"
                                if composee
                                else " avec une valeur issue d un APPEL — plausiblement un "
                                "vrai jeton obtenu du produit puis injecte, ce que fait le "
                                "harnais de cette forge elle-meme. SIGNALE et non bloquant : "
                                "l ecart se lit, il ne s accuse pas. Ce qui reste a verifier "
                                "a la main : que le jeton vient bien du parcours d entree, et "
                                "non d une composition locale passee par une fonction"
                            )
                        ),
                        risque=coter(PAN, identifiant, relatif),
                    )
                )
            for trouve in _COOKIE_POSE.finditer(corps):
                fragment = _cle_de_session(trouve.group("cle"))
                if fragment is None:
                    continue
                identifiant = (
                    f"revue:session-fabriquee-cookie:{relatif}:{nom}:{trouve.group('cle')}"
                )
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.SESSION_FABRIQUEE,
                        localisation=relatif,
                        severite="signale",
                        message=(
                            f"« {nom} » POSE le cookie « {trouve.group('cle')} » (fragment de "
                            f"session « {fragment} ») au lieu de le laisser naitre du parcours "
                            "d entree. Meme geste que l ecriture en localStorage, autre porte : "
                            "SIGNALE, parce qu un cookie pose peut porter une vraie valeur de "
                            "session obtenue ailleurs"
                        ),
                        risque=coter(PAN, identifiant, relatif),
                    )
                )
    return findings


#: Le COROLLAIRE de (7), et le plus coûteux des deux : *la clé qui permet de RELIRE une session
#: doit vivre au même endroit que la session*. Le premier correctif d'Approval2 avait remplacé la
#: fabrication par une vraie connexion par profil — et cassait quand même les cinq workflows,
#: parce que le choix de profil était mémorisé dans `sessionStorage`, que le `storageState` de
#: Playwright NE SAUVEGARDE PAS. Perdu au rejeu, l'application retombait SILENCIEUSEMENT sur son
#: identité nominale. Ce second défaut passait `tsc`, `eslint`, 137 tests unitaires ET le harnais
#: de connexion lui-même ; seule l'exécution réelle des cinq workflows l'a montré.
_STORAGE_STATE = re.compile(r"\bstorageState\b")
_SESSION_STORAGE_ECRITURE = re.compile(r"\bsessionStorage\s*\.\s*setItem\s*\(")
#: Les fichiers de configuration de recette où `storageState` se déclare une fois pour toutes.
_CONFIGS = ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs")


def cle_de_relecture_separee_de_la_session(cible: Path) -> list[Finding]:
    """Corollaire de (7) — un état persisté par `storageState` et une clé écrite ailleurs."""
    specs = _specs(cible)
    if not specs:
        return []
    configs = [
        chemin
        for chemin in sorted(cible.rglob("*"))
        if chemin.is_file() and chemin.name in _CONFIGS and "node_modules" not in chemin.parts
    ]
    textes = {
        f.relative_to(cible).as_posix(): f.read_text(encoding="utf-8", errors="replace")
        for f in [*specs, *configs]
    }
    persiste = sorted(o for o, t in textes.items() if _STORAGE_STATE.search(t))
    if not persiste:
        return []
    findings: list[Finding] = []
    for ou, texte in sorted(textes.items()):
        if not _SESSION_STORAGE_ECRITURE.search(texte):
            continue
        identifiant = f"revue:cle-hors-session:{ou}"
        findings.append(
            Finding(
                id=identifiant,
                classe=classes.SESSION_ET_CLE_SEPAREES,
                localisation=ou,
                message=(
                    f"la recette persiste son etat par `storageState` ({persiste[0]}"
                    f"{' et ' + str(len(persiste) - 1) + ' autre(s)' if len(persiste) > 1 else ''})"
                    f" et ECRIT dans `sessionStorage` ici — or `storageState` ne sauvegarde PAS "
                    "le sessionStorage. La cle est donc PERDUE au rejeu, et l application "
                    "retombe SILENCIEUSEMENT sur son comportement par defaut. La cle qui permet "
                    "de RELIRE une session doit vivre au meme endroit que la session ; les "
                    "separer recree la divergence qu on corrige, sous une forme moins visible. "
                    "Mesure le 24/08 : ce defaut passait tsc, eslint, 137 tests unitaires et le "
                    "harnais de connexion lui-meme"
                ),
                risque=coter(PAN, identifiant, ou),
            )
        )
    return findings


#: TF-0590 (lot Approval2 20260824d) — piège (9), LE SAUT CONDITIONNEL.
#:
#: QUATRE OCCURRENCES DISTINCTES SUR UN MÊME PRODUIT, toutes vertes. Trois tests d'intégration
#: silencieusement ignorés EN INTÉGRATION CONTINUE PENDANT DES MOIS — leurs gardes les faisaient
#: disparaître et l'affichage compact noyait les trois « s » dans 364 points ; l'un d'eux existait
#: *parce qu'une régression réelle était déjà passée*. Puis un saut conditionnel dans la recette
#: d'accessibilité : le rapport disait « 27 passés, 1 sauté » et personne ne regardait lequel.
#:
#: LA DISTINCTION QUI FAIT LA RÈGLE, et sans elle elle serait fausse : un saut INCONDITIONNEL et
#: motivé reste licite. C'est une décision lisible — quelqu'un a écrit « ce test ne tourne pas, et
#: voici pourquoi ». Un saut CONDITIONNEL, lui, peut cesser de tester sans que rien ne change dans
#: le fichier : la condition devient vraie un jour, sur une machine, et le test disparaît. *Un test
#: qui peut cesser de tester sans le dire ment sur la couverture.*
#:
#: PORTÉE ÉLARGIE POUR CETTE RÈGLE SEULE, et le motif est écrit plutôt que subi : les six premières
#: ne lisent que les suites de NAVIGATEUR, faute de cas réel sur les idiomes Python. Ici le cas
#: réel est justement Python (`skipif` sur des tests d'intégration), donc la règle lit les DEUX.
_SUFFIXES_PYTHON = ("_test.py", "test_.py")
_SAUT_CONDITIONNEL = re.compile(
    r"@pytest\.mark\.skipif\s*\("                       # Python : la forme du cas fondateur
    r"|\bpytest\.skip\s*\([^)]*\)\s*if\b"
    r"|\btest\.skip\s*\(\s*(?!\s*\))[^)]*[<>=!]"        # Playwright : test.skip(<condition>)
    r"|\btest\.skip\s*\(\s*(?:!|Boolean\(|process\.env|await |[a-z_$][\w.$]*\s*(?:\)|,))",
    re.IGNORECASE,
)
#: Un saut INCONDITIONNEL — licite, et donc explicitement reconnu pour ne pas être confondu.
_SAUT_ASSUME = re.compile(
    r"@pytest\.mark\.skip\s*\(\s*reason\s*="
    r"|\btest\.skip\s*\(\s*\)"
    r"|\bit\.skip\s*\(|\bdescribe\.skip\s*\(",
)


def _fichiers_de_test(cible: Path) -> list[Path]:
    """Les suites de navigateur ET les suites Python — pour la règle (9) seulement."""
    fichiers = list(_specs(cible))
    for chemin in sorted(cible.rglob("*.py")):
        if "node_modules" in chemin.parts or ".venv" in chemin.parts:
            continue
        nom = chemin.name
        if nom.startswith("test_") or nom.endswith("_test.py"):
            fichiers.append(chemin)
    return fichiers


def saut_conditionnel(cible: Path) -> list[Finding]:
    """Piège 9 — un saut qui peut cesser de tester sans que rien ne le dise.

    *Règle : un saut CONDITIONNEL est interdit en intégration continue. Ou le préalable est
    garanti par le harnais, ou son absence est un ÉCHEC EXPLICITE qui nomme ce qui manque. Un
    saut inconditionnel et motivé reste licite : c'est une décision, pas une disparition.*
    """
    findings: list[Finding] = []
    for fichier in _fichiers_de_test(cible):
        relatif = fichier.relative_to(cible).as_posix()
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for numero, ligne in enumerate(texte.splitlines(), start=1):
            if not _SAUT_CONDITIONNEL.search(ligne):
                continue
            if _SAUT_ASSUME.search(ligne):
                continue
            identifiant = f"revue:saut-conditionnel:{relatif}:{numero}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.SAUT_CONDITIONNEL,
                    localisation=f"{relatif}:{numero}",
                    message=(
                        f"saut CONDITIONNEL ligne {numero} : « {ligne.strip()[:90]} ». Un test qui "
                        "peut cesser de tester sans que rien ne change dans le fichier MENT sur la "
                        "couverture — la condition devient vraie un jour, sur une machine, et le "
                        "cas disparait. Ou le prealable est GARANTI par le harnais, ou son absence "
                        "est un ECHEC EXPLICITE qui nomme ce qui manque. Un saut INCONDITIONNEL et "
                        "motive reste licite : c est une decision lisible, pas une disparition. "
                        "Mesure : trois tests d integration ignores en integration continue "
                        "PENDANT DES MOIS, dont un ecrit parce qu une regression reelle etait "
                        "deja passee ; et un rapport disant « 27 passes, 1 saute » que personne "
                        "ne lisait"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )
    return findings


def analyser_suite(cible: Path) -> list[Finding]:
    """Les huit règles mécanisables (sur neuf), sur les suites du projet. Aucune exécution,
    aucun réseau — un projet dont la suite ne peut pas tourner est justement celui où un faux
    vert dort le plus longtemps."""
    return [
        *absence_sans_presence(cible),
        *motif_satisfait_par_le_declencheur(cible),
        *donnees_recopiees(cible),
        *prefixe_d_un_chemin_valide(cible),
        *trous_de_couverture_inter_suites(cible),
        *session_fabriquee(cible),
        *cle_de_relecture_separee_de_la_session(cible),
        *saut_conditionnel(cible),
    ]
