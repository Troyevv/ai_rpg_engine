import {useReducedMotion, type Variants} from 'framer-motion';

export const motionTiming={fast:.14, normal:.24, slow:.48};
export const ease=[.22,1,.36,1] as const;
const transition={duration:motionTiming.normal,ease};
export const motionPresets:Record<string,Variants>={
 fade:{hidden:{opacity:0},visible:{opacity:1,transition},exit:{opacity:0,transition:{duration:motionTiming.fast}}},
 fadeUp:{hidden:{opacity:0,y:8},visible:{opacity:1,y:0,transition}},
 fadeDown:{hidden:{opacity:0,y:-8},visible:{opacity:1,y:0,transition}},
 scaleIn:{hidden:{opacity:0,scale:.98},visible:{opacity:1,scale:1,transition}},
 panelSlide:{hidden:{opacity:0,x:24},visible:{opacity:1,x:0,transition}},
 staggerContainer:{hidden:{opacity:0},visible:{opacity:1,transition:{staggerChildren:.045}}},
 staggerItem:{hidden:{opacity:0,y:5},visible:{opacity:1,y:0,transition:{duration:motionTiming.fast,ease}}},
 sceneTransition:{hidden:{opacity:0,y:6},visible:{opacity:1,y:0,transition}},
 povTransition:{hidden:{opacity:0,y:10},visible:{opacity:1,y:0,transition:{duration:motionTiming.slow,ease}}},
};
export function useMotionPreset(name:keyof typeof motionPresets){
 const reduced=useReducedMotion();
 // MotionConfig disables transforms; this also removes stagger and long transitions.
 return reduced?motionPresets.fade:motionPresets[name];
}
