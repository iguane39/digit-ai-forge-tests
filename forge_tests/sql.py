"""Lecture du SQL — FILTRER les commentaires AVANT de découper les instructions.

RT-8, constaté en production sur `0004_catalogues.sql` : l adaptateur Migrations découpait la
section sur `;` puis rejetait les fragments commençant par `--`. Un `;` posé DANS un
commentaire fabriquait donc une instruction qui n avait jamais existé — jamais envoyée au
moteur, donc jamais retrouvée dans le relevé de la sonde, donc migration déclarée non exercée.
Un FAIL à tort, produit par le lecteur et non par le projet audité.

Le même motif « parser avant filtrer » vivait dans TROIS autres endroits du dépôt, tous
corrigés en s appuyant sur ce module :
  - `adaptateurs/data.py` : les expressions régulières d inventaire (CREATE TABLE, CONSTRAINT,
    INDEX, TRIGGER, NOT NULL) lisaient le texte brut — une table mise en commentaire entrait
    donc à l inventaire et devenait un élément « jamais exercé » impossible à couvrir ;
  - `adaptateurs/migrations.py` : les objets ANNONCÉS par une section étaient relevés de la
    même façon, y compris depuis un `CREATE TABLE` commenté ;
  - `sondes/verifier_schema.py` : la sonde qui rejoue les migrations sur une base neuve
    découpait naïvement sur `;` — un commentaire porteur d un `;` lui faisait envoyer un
    fragment vide au moteur, et l introspection du schéma entier échouait.

Le découpage est conscient des littéraux : un `;`, un `--` ou un `/*` placé dans une chaîne
`'…'` ou un identifiant `"…"` ne coupe rien et ne masque rien.
"""

from __future__ import annotations

NON_JUGE = [
    "sql : le decoupage reconnait les litteraux `'...'` (echappement `''`) et les identifiants "
    "entre guillemets ; un `;` ou un `--` place dans un litteral DOLLAR-QUOTE (`$$...$$`, corps "
    "de fonction PL/pgSQL) ou dans une chaine a echappement backslash (`E'...\\'...'`) reste "
    "hors de portee — l instruction serait coupee au mauvais endroit",
    "sql : ce module lit le TEXTE des migrations, il ne l analyse pas grammaticalement — une "
    "instruction syntaxiquement invalide est rendue telle quelle, sans jugement",
]

_DELIMITEURS = ("'", '"')


def _fin_litteral(texte: str, debut: int) -> int:
    """Indice juste après le littéral ou l identifiant qui commence en `debut`.

    Un délimiteur doublé (`''`, `""`) est un échappement, pas une fermeture. Un littéral non
    fermé rend la fin du texte : le lecteur dégrade, il ne lève jamais d IndexError.
    """
    delimiteur = texte[debut]
    indice, fin = debut + 1, len(texte)
    while indice < fin:
        if texte[indice] == delimiteur:
            if indice + 1 < fin and texte[indice + 1] == delimiteur:
                indice += 2
                continue
            return indice + 1
        indice += 1
    return fin


def sans_commentaires(texte: str) -> str:
    """Le même SQL, commentaires de ligne (`--`) et de bloc (`/* */`) retirés.

    Le commentaire est remplacé par un blanc, jamais supprimé sans trace : sans cela
    `CREATE INDEX i -- note\\n ON t (c)` deviendrait `CREATE INDEX i ON t (c)` collé.
    """
    morceaux: list[str] = []
    indice, fin = 0, len(texte)
    while indice < fin:
        caractere = texte[indice]
        if caractere in _DELIMITEURS:
            suivant = _fin_litteral(texte, indice)
            morceaux.append(texte[indice:suivant])
            indice = suivant
            continue
        if texte.startswith("--", indice):
            saut = texte.find("\n", indice)
            morceaux.append("\n")
            indice = fin if saut == -1 else saut + 1
            continue
        if texte.startswith("/*", indice):
            cloture = texte.find("*/", indice + 2)
            morceaux.append(" ")
            indice = fin if cloture == -1 else cloture + 2
            continue
        morceaux.append(caractere)
        indice += 1
    return "".join(morceaux)


def decouper(texte: str) -> list[str]:
    """Instructions d un fragment SQL, normalisées, dans l ordre.

    Commentaires retirés d abord, découpage ensuite : c est tout le correctif RT-8. Le `;`
    n est un séparateur que hors littéral.
    """
    propre = sans_commentaires(texte)
    instructions: list[str] = []
    courante: list[str] = []
    indice, fin = 0, len(propre)
    while indice < fin:
        caractere = propre[indice]
        if caractere in _DELIMITEURS:
            suivant = _fin_litteral(propre, indice)
            courante.append(propre[indice:suivant])
            indice = suivant
            continue
        if caractere == ";":
            instructions.append("".join(courante))
            courante = []
            indice += 1
            continue
        courante.append(caractere)
        indice += 1
    instructions.append("".join(courante))
    return [" ".join(brute.split()) for brute in instructions if brute.strip()]
