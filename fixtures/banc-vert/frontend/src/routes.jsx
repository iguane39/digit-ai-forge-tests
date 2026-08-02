// Table de routage du banc — 5 routes. Source d enumeration de la surface Front.
import Accueil from "./pages/Accueil.jsx";
import Login from "./pages/Login.jsx";
import Commandes from "./pages/Commandes.jsx";
import CommandeDetail from "./pages/CommandeDetail.jsx";
import Admin from "./pages/Admin.jsx";

export const routes = [
  { path: "/", element: <Accueil /> },
  { path: "/login", element: <Login /> },
  { path: "/commandes", element: <Commandes /> },
  { path: "/commandes/:id", element: <CommandeDetail /> },
  { path: "/admin", element: <Admin /> },
];
