-- +migrate Up
-- RT-8 : ce commentaire contient un point-virgule ; il ne doit fabriquer AUCUNE instruction.
CREATE UNIQUE INDEX utilisateur_email_idx
  -- unicite stricte ; posee apres le socle.
  ON utilisateur (email);
/* Commentaire de bloc, porteur lui aussi d un point-virgule ; et de plusieurs lignes.
   Rien de tout ceci ne doit etre envoye au moteur. */
COMMENT ON INDEX utilisateur_email_idx IS 'un seul compte par adresse ; unicite metier';

-- +migrate Down
COMMENT ON INDEX utilisateur_email_idx IS NULL;
DROP INDEX utilisateur_email_idx;  -- fin de section ;
