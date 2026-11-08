import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/readex-pro";
import "@fontsource-variable/reem-kufi";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
