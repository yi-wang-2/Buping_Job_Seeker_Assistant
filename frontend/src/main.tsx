import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import CloudApp from "./CloudApp";
import "./index.css";

const RootApp = import.meta.env.VITE_DEPLOYMENT_MODE === "cloud" ? CloudApp : App;

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <RootApp />
    </BrowserRouter>
  </React.StrictMode>,
);
