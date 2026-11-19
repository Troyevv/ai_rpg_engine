import {MotionConfig} from "framer-motion";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user"><App /></MotionConfig>
  </React.StrictMode>,
);

if(import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext){
 window.addEventListener('load',()=>{void navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(()=>{/* Browser access remains available if installation is unsupported. */})});
}
