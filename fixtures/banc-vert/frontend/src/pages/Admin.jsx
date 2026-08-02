export default function Admin() {
  return (
    <section>
      <input data-testid="import-fichier" type="file" />
      <button data-testid="bouton-cloture">Cloturer la journee</button>
      <button data-testid="bouton-purge">Purger</button>
      <select data-testid="filtre-utilisateur" />
    </section>
  );
}
