// Route `/en` du site versionne (convention pages router). Sans ces trois pages, les
// destinations du menu anglais ne seraient dans AUCUNE arborescence enumerable et le controle
// des liens de composants les declarerait cassees — un autre defaut que celui qu on plante ici.
export default function Home() {
  return <main>Welcome to the red bench</main>;
}
