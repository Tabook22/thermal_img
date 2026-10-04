import {describe,it,expect} from 'vitest';
import {normalizeMaximumRing} from './maximumRing';
describe('maximum highlight geometry',()=>{
  it('allows an offset while keeping the hottest pixel inside',()=>{
    const ring=normalizeMaximumRing({dx:.1,dy:.1,radius:.05});
    expect(Math.hypot(ring.dx,ring.dy)).toBeCloseTo(.05*.85);
  });
  it('shrinking brings the ring back around its fixed anchor',()=>{
    const ring=normalizeMaximumRing({dx:.04,dy:0,radius:.01});
    expect(ring.dx).toBeCloseTo(.0085);expect(ring.radius).toBe(.01);
  });
  it('bounds imported values and restores a usable default',()=>{
    expect(normalizeMaximumRing({radius:NaN,dx:Infinity})).toEqual({dx:0,dy:0,radius:.02});
    expect(normalizeMaximumRing({radius:4}).radius).toBe(.25);
  });
});
