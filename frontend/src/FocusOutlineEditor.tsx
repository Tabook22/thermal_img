import {useId,useRef,useState,useLayoutEffect,type PointerEvent} from 'react';
import type {FocusPoint,FocusStroke,InsulatorFocus} from './InsulatorFocus';

type Selection={points:FocusPoint[];strokes:FocusStroke[]};
/** All coordinates are normalized to the source frame; zoom/scroll never enter saved geometry. */
export default function FocusOutlineEditor({src,initial,busy,onPreview,onCancel}:{src:string;initial?:InsulatorFocus|null;busy:boolean;onPreview:(points:FocusPoint[],strokes:FocusStroke[])=>void;onCancel:()=>void}){
 const seed:Selection={points:initial?.points||[],strokes:initial?.strokes||[]};
 const [selection,setSelection]=useState<Selection>(seed),[past,setPast]=useState<Selection[]>([]),[future,setFuture]=useState<Selection[]>([]);
 const [mode,setMode]=useState<'polygon'|'add'|'erase'|'pan'>('polygon'),[zoom,setZoom]=useState(1),[radius,setRadius]=useState(.015),[ratio,setRatio]=useState(.8),[visible,setVisible]=useState(true);
 const [draft,setDraft]=useState<FocusStroke|null>(null),[cursor,setCursor]=useState<FocusPoint|null>(null);
 const gesture=useRef<{stroke?:FocusStroke;x:number;y:number;left:number;top:number}|null>(null),viewport=useRef<HTMLDivElement>(null);
 const [frame,setFrame]=useState({width:540,height:380});
 useLayoutEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>setFrame({width:el.clientWidth,height:el.clientHeight}));observer.observe(el);return()=>observer.disconnect()},[]);
 const maskId=useId().replace(/:/g,'');
 const commit=(next:Selection)=>{setPast(p=>[...p.slice(-59),selection]);setFuture([]);setSelection(next)};
 const point=(e:PointerEvent<SVGSVGElement>)=>{const r=e.currentTarget.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}};
 const start=(e:PointerEvent<SVGSVGElement>)=>{if(busy||e.button!==0)return;e.preventDefault();const p=point(e);
  if(mode==='polygon'){if(selection.points.length<256)commit({...selection,points:[...selection.points,p]});return}
  if(mode!=='pan'&&(selection.points.length<3||selection.strokes.length>=200))return;
  e.currentTarget.setPointerCapture(e.pointerId);const stroke=mode==='pan'?undefined:{points:[p],radius,erase:mode==='erase'};
  gesture.current={stroke,x:e.clientX,y:e.clientY,left:viewport.current?.scrollLeft||0,top:viewport.current?.scrollTop||0};if(stroke)setDraft(stroke);
 };
 const move=(e:PointerEvent<SVGSVGElement>)=>{const p=point(e);setCursor(p);const g=gesture.current;if(!g)return;
  if(!g.stroke){if(viewport.current){viewport.current.scrollLeft=g.left+g.x-e.clientX;viewport.current.scrollTop=g.top+g.y-e.clientY}return}
  if(g.stroke.points.length<1000){g.stroke={...g.stroke,points:[...g.stroke.points,p]};setDraft(g.stroke)}
 };
 const finish=()=>{const g=gesture.current;gesture.current=null;setDraft(null);if(g?.stroke)commit({...selection,strokes:[...selection.strokes,g.stroke]})};
 const path=(points:FocusPoint[])=>points.map((p,i)=>`${i?'L':'M'}${p.x*1000} ${p.y*ratio*1000}`).join(' ');
 const strokes=[...selection.strokes,...(draft?[draft]:[])];
 return <div className="focusOutlineEditor">
  <p><b>Trace the insulator, then refine between the discs.</b> Include fittings or conductors if needed. Add/erase brushes edit the mask; measurements use its exact boundary.</p>
  <div className="focusEditToolbar" role="toolbar" aria-label="Insulator selection tools">{(['polygon','add','erase','pan'] as const).map(tool=><button type="button" key={tool} disabled={busy} aria-pressed={mode===tool} onClick={()=>setMode(tool)}>{({polygon:'Polygon',add:'Add brush',erase:'Erase brush',pan:'Pan'})[tool]}</button>)}<button type="button" aria-label="Zoom selection out" disabled={zoom<=1} onClick={()=>setZoom(z=>Math.max(1,z-.5))}>−</button><span>{zoom.toFixed(1)}×</span><button type="button" aria-label="Zoom selection in" disabled={zoom>=6} onClick={()=>setZoom(z=>Math.min(6,z+.5))}>+</button><button type="button" onClick={()=>setZoom(1)}>Fit</button></div>
  {(mode==='add'||mode==='erase')&&<label className="focusBrushSize">Brush size <input type="range" aria-label="Selection brush size" min=".001" max=".08" step=".001" value={radius} onChange={e=>setRadius(+e.target.value)}/><span>{(radius*200).toFixed(1)}% of image width</span></label>}
  <div ref={viewport} className="focusEditViewport"><div className="focusOutlineImage" style={{width:`${Math.min(frame.width,frame.height/ratio)*zoom}px`,maxWidth:'none',margin:zoom===1?'auto':'0'}}><img src={src} alt="Full image: outline and brush the insulator" draggable={false} onLoad={e=>setRatio(e.currentTarget.naturalHeight/e.currentTarget.naturalWidth)}/>
   <svg viewBox={`0 0 1000 ${1000*ratio}`} preserveAspectRatio="none" aria-label="Click to outline or brush the insulator" style={{cursor:mode==='pan'?'grab':'crosshair'}} onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={()=>{gesture.current=null;setDraft(null)}} onPointerLeave={()=>setCursor(null)}>
    <defs><mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="1000" height={1000*ratio}><rect width="1000" height={1000*ratio} fill="black"/><polygon style={{fill:'white',stroke:'none'}} points={selection.points.map(p=>`${p.x*1000},${p.y*ratio*1000}`).join(' ')}/>{strokes.map((s,i)=><g key={i}>{s.points.length===1?<circle style={{fill:s.erase?'black':'white',stroke:'none'}} cx={s.points[0].x*1000} cy={s.points[0].y*ratio*1000} r={s.radius*1000}/>:<path d={path(s.points)} fill="none" stroke={s.erase?'black':'white'} strokeWidth={s.radius*2000} strokeLinecap="round" strokeLinejoin="round"/>}</g>)}</mask></defs>
    {visible&&<rect width="1000" height={1000*ratio} fill="#6befdc" fillOpacity=".3" mask={`url(#${maskId})`}/>}
    {mode==='polygon'&&<><polyline fill="none" stroke="#6befdc" strokeWidth="1.5" vectorEffect="non-scaling-stroke" points={selection.points.map(p=>`${p.x*1000},${p.y*ratio*1000}`).join(' ')}/>{selection.points.map((p,i)=><circle key={i} cx={p.x*1000} cy={p.y*ratio*1000} r={3/zoom}/>)}</>}
    {cursor&&(mode==='add'||mode==='erase')&&<circle style={{fill:'none',stroke:mode==='erase'?'#ff827b':'#fff'}} cx={cursor.x*1000} cy={cursor.y*ratio*1000} r={radius*1000} vectorEffect="non-scaling-stroke"/>}
   </svg>
  </div></div>
  <div className="focusEditToolbar"><span role="status">{selection.points.length} points · {selection.strokes.length} brush strokes</span><button type="button" disabled={busy||!past.length} onClick={()=>{setFuture(f=>[selection,...f]);setSelection(past.at(-1)!);setPast(p=>p.slice(0,-1))}}>Undo selection</button><button type="button" disabled={busy||!future.length} onClick={()=>{setPast(p=>[...p,selection]);setSelection(future[0]);setFuture(f=>f.slice(1))}}>Redo selection</button><button type="button" disabled={busy} onClick={()=>commit({points:[],strokes:[]})}>Clear</button><button type="button" disabled={busy} onClick={()=>commit(seed)}>Reset selection</button><label><input type="checkbox" checked={visible} onChange={e=>setVisible(e.target.checked)}/>Mask preview</label></div>
  <div className="focusOutlineActions"><button type="button" disabled={busy} onClick={onCancel}>Cancel outline</button><button type="button" className="primary" disabled={busy||selection.points.length<3} onClick={()=>onPreview(selection.points,selection.strokes)}>{busy?'Preparing preview…':'2. Preview blue background'}</button></div>
 </div>;
}
