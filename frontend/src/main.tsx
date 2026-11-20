import {GestureHost} from './gestures/Controls';
import {MotionConfig} from "framer-motion";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./styles/gestures.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user"><GestureHost/><App /></MotionConfig>
  </React.StrictMode>,
);

if(import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext){
 window.addEventListener('load',()=>{void navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(()=>{/* Browser access remains available if installation is unsupported. */})});
}
