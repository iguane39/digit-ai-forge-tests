-- +migrate Up
-- Banc ROUGE de la fabrique de données (TF-2012), courriel réel : le schéma n admet que deux
-- adresses d expédition, sous un domaine ENREGISTRÉ (example.com, qui ne désigne personne mais
-- n est pas un domaine réservé au sens du garde-fou : seuls .test et .invalid le sont). La
-- fabrique est obligée de reprendre l une d elles : le garde-fou de jeux.py doit refuser le jeu
-- entier AVANT toute écriture, en nommant la vérification qui impose la valeur.
CREATE TABLE notification (
  id SERIAL PRIMARY KEY,
  expediteur TEXT NOT NULL
    CHECK (expediteur IN ('ne-pas-repondre@example.com', 'support@example.com')),
  sujet TEXT NOT NULL
);

-- +migrate Down
DROP TABLE notification;
