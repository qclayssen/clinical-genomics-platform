import React from "react";
import ReactDOM from "react-dom/client";
import { VariantReview } from "./pages/VariantReview";
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <VariantReview />
  </React.StrictMode>,
);
