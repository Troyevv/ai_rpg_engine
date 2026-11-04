import {afterEach,expect,it,vi} from 'vitest';
import {animateFog} from '../src/lib/fogRenderer';
afterEach(()=>vi.restoreAllMocks());
it('shares one clock, caps work, suspends in a hidden tab, and releases the last row',()=>{
 let callback:FrameRequestCallback|undefined;let id=0;
 const request=vi.spyOn(globalThis,'requestAnimationFrame').mockImplementation(cb=>{callback=cb;return ++id});
 const cancel=vi.spyOn(globalThis,'cancelAnimationFrame').mockImplementation(()=>{callback=undefined});
 const first=vi.fn(),second=vi.fn();
 const stopA=animateFog(first),stopB=animateFog(second);
 expect(request).toHaveBeenCalledTimes(1);
 callback!(1000);callback!(1010);expect(first).toHaveBeenCalledTimes(1);expect(second).toHaveBeenCalledTimes(1);
 stopA();callback!(1050);expect(first).toHaveBeenCalledTimes(1);expect(second).toHaveBeenCalledTimes(2);
 const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(true);
 document.dispatchEvent(new Event('visibilitychange'));expect(callback).toBeUndefined();
 hidden.mockReturnValue(false);document.dispatchEvent(new Event('visibilitychange'));
 callback!(2000);expect(second).toHaveBeenCalledTimes(3);
 stopB();expect(cancel).toHaveBeenCalled();expect(callback).toBeUndefined();
});
