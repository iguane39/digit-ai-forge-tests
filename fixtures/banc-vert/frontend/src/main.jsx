import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { routes } from "./routes.jsx";

function Application() {
  return (
    <BrowserRouter>
      <nav><Link to="/">Accueil</Link></nav>
      <Routes>
        {routes.map((r) => (<Route key={r.path} path={r.path} element={r.element} />))}
      </Routes>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("racine")).render(<Application />);
