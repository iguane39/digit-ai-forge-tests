-- +migrate Up
-- Banc ROUGE de la fabrique de données (TF-2012), violation : la référence d un dossier suit un
-- motif (expression régulière). La fabrique ne traduit pas un motif en valeurs : elle NOMME la
-- vérification au rapport, et c est le chargement réel qui doit attraper le rejet. Un juge qui
-- passerait ce jeu au vert ne jugerait rien.
CREATE TABLE dossier (
  id SERIAL PRIMARY KEY,
  reference TEXT NOT NULL,
  ouvert_le DATE NOT NULL,
  CONSTRAINT dossier_reference_format CHECK (reference ~ '^DOS-[0-9]{6}$')
);

CREATE TABLE piece (
  id SERIAL PRIMARY KEY,
  dossier_id INTEGER NOT NULL REFERENCES dossier (id),
  libelle TEXT NOT NULL
);

-- +migrate Down
DROP TABLE piece;
DROP TABLE dossier;
