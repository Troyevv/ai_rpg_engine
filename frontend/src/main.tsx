import {MotionConfig} from "framer-motion";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./styles/view-controls.css";
import "./styles/narrative-choices.css";
// Retire client-only preferences from earlier PR builds.
try {
  localStorage.removeItem('interface.gestures.v1');
  localStorage.removeItem('interface.gesture-learning.v1');
} catch { /* Storage can be unavailable in private browsing. */ }

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user"><App /></MotionConfig>
  </React.StrictMode>,
);

if(import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext){
 window.addEventListener('load',()=>{void navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(()=>{/* Browser access remains available if installation is unsupported. */})});
}
