import {vi} from 'vitest';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
Object.defineProperty(window,'matchMedia',{value:vi.fn(()=>({matches:false,addListener:vi.fn(),removeListener:vi.fn()}))});
