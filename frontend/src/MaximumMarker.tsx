import {useEffect,useRef,useState,type PointerEvent} from 'react';
import {normalizeMaximumRing,type MaximumRing} from './maximumRing';
import './maximum-marker.css';

export default function MaximumMarker({point,value,width,height,layout,editable,onChange,onCommit}:{point:{x:number;y:number};value:number;width:number;height:number;layout?:MaximumRing;editable:boolean;onChange:(value:MaximumRing|undefined)=>void;onCommit:(before:MaximumRing|undefined,after:MaximumRing)=>void}){
  const root=useRef<HTMLDivElement>(null),[selected,setSelected]=useState(false);
  const ring=normalizeMaximumRing(layout),cx=point.x+.5+ring.dx*width,cy=point.y+.5+ring.dy*width,r=ring.radius*width;
  const drag=useRef<{id:number;mode:'move'|'resize';x:number;y:number;displayWidth:number;before:MaximumRing|undefined;start:MaximumRing;latest:MaximumRing}|null>(null);
  useEffect(()=>{if(!selected)return;const outside=(e:globalThis.PointerEvent)=>{if(!root.current?.contains(e.target as Node))setSelected(false)};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside)},[selected]);
  const begin=(e:PointerEvent,mode:'move'|'resize')=>{if(!editable||e.button!==0)return;e.preventDefault();e.stopPropagation();setSelected(true);e.currentTarget.setPointerCapture(e.pointerId);drag.current={id:e.pointerId,mode,x:e.clientX,y:e.clientY,displayWidth:root.current!.getBoundingClientRect().width,before:layout,start:ring,latest:ring}};
  const move=(e:PointerEvent)=>{const d=drag.current;if(!d||d.id!==e.pointerId)return;e.preventDefault();e.stopPropagation();const dx=(e.clientX-d.x)/d.displayWidth,dy=(e.clientY-d.y)/d.displayWidth;
    d.latest=normalizeMaximumRing(d.mode==='move'?{...d.start,dx:d.start.dx+dx,dy:d.start.dy+dy}:{...d.start,radius:Math.hypot(d.start.radius/Math.SQRT2+dx,d.start.radius/Math.SQRT2+dy)});onChange(d.latest)};
  const end=(e:PointerEvent)=>{const d=drag.current;if(!d||d.id!==e.pointerId)return;move(e);drag.current=null;if(JSON.stringify(normalizeMaximumRing(d.before))===JSON.stringify(d.latest))onChange(d.before);else onCommit(d.before,d.latest)};
  const cancel=(e:PointerEvent)=>{const d=drag.current;if(d?.id!==e.pointerId)return;e.stopPropagation();drag.current=null;onChange(d.before)};
  const change=(value:MaximumRing)=>{const next=normalizeMaximumRing(value);if(JSON.stringify(ring)===JSON.stringify(next))return;onChange(next);onCommit(layout,next)};
  const left=(point.x+.5)/width*100,top=(point.y+.5)/height*100,flip=left>65;
  return <div ref={root} className="maximumMarker">
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label="Maximum temperature highlight">
      <circle cx={cx} cy={cy} r={r} className="maxRingOutline"/>
      <circle cx={cx} cy={cy} r={r} className="maxRingHit" style={{pointerEvents:editable?'stroke':'none'}} role="button" tabIndex={editable?0:-1} aria-label="Move or resize maximum temperature circle" aria-pressed={selected} onFocus={()=>setSelected(true)} onPointerDown={e=>begin(e,'move')} onPointerMove={move} onPointerUp={end} onPointerCancel={cancel} onKeyDown={e=>{if(!editable)return;const step=(e.shiftKey?5:1)/width;let next:MaximumRing|undefined;if(e.key==='ArrowLeft')next={...ring,dx:ring.dx-step};if(e.key==='ArrowRight')next={...ring,dx:ring.dx+step};if(e.key==='ArrowUp')next={...ring,dy:ring.dy-step};if(e.key==='ArrowDown')next={...ring,dy:ring.dy+step};if(e.key==='+'||e.key==='=')next={...ring,radius:ring.radius*1.15};if(e.key==='-')next={...ring,radius:ring.radius/1.15};if(e.key==='Escape')setSelected(false);if(next){e.preventDefault();e.stopPropagation();change(next)}}}><title>Drag the hollow circle. The maximum stays fixed. Select to resize.</title></circle>
      <path d={`M ${point.x-2.5} ${point.y+.5} h 6 M ${point.x+.5} ${point.y-2.5} v 6`} className="maxPixelAnchor"/>
      {selected&&editable&&<circle cx={cx+r/Math.SQRT2} cy={cy+r/Math.SQRT2} r={5} className="maxRingHandle" aria-label="Resize maximum temperature circle" onPointerDown={e=>begin(e,'resize')} onPointerMove={move} onPointerUp={end} onPointerCancel={cancel}/>}
    </svg>
    <b className={`maxReading ${flip?'flip':''}`} style={{left:`${left}%`,top:`${top}%`}}>H {value.toFixed(1)}°C</b>
    {selected&&editable&&<div className={`maxRingControls ${flip?'flip':''}`} style={{left:`${left}%`,top:`${Math.max(0,(cy-r)/height*100)}%`}} onPointerDown={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape')setSelected(false);else if(!e.ctrlKey&&!e.metaKey)e.stopPropagation()}}>
      <button aria-label="Decrease maximum circle size" title="Smaller circle" onClick={()=>change({...ring,radius:ring.radius/1.2})}>−</button><button aria-label="Increase maximum circle size" title="Larger circle" onClick={()=>change({...ring,radius:ring.radius*1.2})}>+</button><button title="Center the circle on the hottest pixel and restore its size" onClick={()=>change({dx:0,dy:0,radius:.02})}>Reset</button><small>Circle only · MAX stays fixed</small>
    </div>}
  </div>;
}
