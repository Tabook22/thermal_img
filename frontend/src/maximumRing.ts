export type MaximumRing = {dx:number;dy:number;radius:number};
export const defaultMaximumRing:MaximumRing={dx:0,dy:0,radius:.02};
// Offsets and radius use image-width units, independent of canvas zoom.
// Keep the measured pixel comfortably inside the presentation ring.
export function normalizeMaximumRing(value?:Partial<MaximumRing>):MaximumRing{
  const finite=(v:unknown,fallback:number)=>typeof v==='number'&&Number.isFinite(v)?v:fallback;
  const radius=Math.max(.008,Math.min(.25,finite(value?.radius,.02)));
  let dx=finite(value?.dx,0),dy=finite(value?.dy,0);
  const distance=Math.hypot(dx,dy),limit=radius*.85;
  if(distance>limit){dx*=limit/distance;dy*=limit/distance}
  return {dx,dy,radius};
}
