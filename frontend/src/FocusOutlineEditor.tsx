import {useState} from 'react';
import type {FocusPoint} from './InsulatorFocus';

/** Draft selection only: no workspace settings change until the preview is applied. */
export default function FocusOutlineEditor({src,busy,onPreview,onCancel}:{src:string;busy:boolean;onPreview:(points:FocusPoint[])=>void;onCancel:()=>void}){
 const [points,setPoints]=useState<FocusPoint[]>([]);
 return <div className="focusOutlineEditor">
  <p><b>Click around the insulator’s outside edge.</b> Add points from top to bottom and back up the other side. Include all the discs. The surrounding scene will stay visible in muted blue.</p>
  <div className="focusOutlineImage"><img src={src} alt="Full image: click around the insulator to keep" draggable={false}/>
   <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Click to outline the insulator" onPointerDown={e=>{if(busy||e.button!==0||points.length>=64)return;e.preventDefault();const r=e.currentTarget.getBoundingClientRect();setPoints(p=>[...p,{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}])}}>
    <polygon points={points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>
    {points.map((p,i)=><circle key={i} cx={p.x*1000} cy={p.y*1000} r="5"/>)}
   </svg>
  </div>
  <div className="focusOutlineActions"><span role="status">{points.length} points · minimum 3</span><button type="button" disabled={busy||!points.length} onClick={()=>setPoints(p=>p.slice(0,-1))}>Undo point</button><button type="button" disabled={busy} onClick={()=>setPoints([])}>Start again</button></div>
  <div className="focusOutlineActions"><button type="button" disabled={busy} onClick={onCancel}>Cancel outline</button><button type="button" className="primary" disabled={busy||points.length<3} onClick={()=>onPreview(points)}>{busy?'Preparing preview…':'2. Preview blue background'}</button></div>
 </div>;
}
