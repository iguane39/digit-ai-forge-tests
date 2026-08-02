export default function Admin() {
  return (
    <section>
      <input data-testid="import-fichier" type="file" aria-label="Fichier a importer" />
      <button data-testid="bouton-cloture">Cloturer la journee</button>
      <button data-testid="bouton-purge">Purger</button>
      <select data-testid="filtre-utilisateur" defaultValue="chef" aria-label="Filtrer par utilisateur">
        <option value="chef">Chef</option>
      </select>
    </section>
  );
}
