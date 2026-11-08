import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/readex-pro";
import "@fontsource-variable/reem-kufi";
import "@fontsource-variable/lora";
import "@fontsource-variable/lora/wght-italic.css";
import "@fontsource-variable/inter";
import "@fontsource-variable/space-grotesk";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
