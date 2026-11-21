import {useAnimations,turnTimes} from './lib/animations';
import {MotionConfig} from "framer-motion";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./styles/view-controls.css";
import "./styles/narrative-choices.css";
import "./styles/narrative-v3.css";
// Retire client-only preferences from earlier PR builds.
try {
  localStorage.removeItem('interface.gestures.v1');
  localStorage.removeItem('interface.gesture-learning.v1');
} catch { /* Storage can be unavailable in private browsing. */ }

function Presentation(){
 const animations=useAnimations(),times=turnTimes.useValue();
 React.useLayoutEffect(()=>{document.documentElement.toggleAttribute('data-hide-turn-times',!times)},[times]);
 React.useLayoutEffect(()=>{document.documentElement.toggleAttribute('data-no-motion',!animations)},[animations]);
 return <MotionConfig reducedMotion={animations?'user':'always'}><App/></MotionConfig>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Presentation/>
  </React.StrictMode>,
);

if(import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext){
 window.addEventListener('load',()=>{void navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(()=>{/* Browser access remains available if installation is unsupported. */})});
}
