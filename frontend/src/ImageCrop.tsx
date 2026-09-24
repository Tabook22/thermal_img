import {useEffect,useRef,useState} from 'react';
import {apiFetch} from './api';
import './image-crop.css';

export type ImageCrop={x:number;y:number;width:number;height:number};
const full:ImageCrop={x:0,y:0,width:1,height:1};
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n));
export function cropFromPoints(a:{x:number;y:number},b:{x:number;y:number}):ImageCrop{
  const x=clamp(Math.min(a.x,b.x),0,.99),y=clamp(Math.min(a.y,b.y),0,.99);
  return {x,y,width:clamp(Math.abs(a.x-b.x),.01,1-x),height:clamp(Math.abs(a.y-b.y),.01,1-y)};
}

export default function ImageCropEditor({imageId,payload,crop,onApply,onClose}:{imageId:number;payload:unknown;crop:ImageCrop|null;onApply:(crop:ImageCrop|null)=>void;onClose:()=>void}){
  const dialog=useRef<HTMLDialogElement>(null),surface=useRef<HTMLDivElement>(null),scroll=useRef<HTMLDivElement>(null);
  const [selection,setSelection]=useState<ImageCrop>(crop||{x:.1,y:.1,width:.8,height:.8}),[zoom,setZoom]=useState(100),[preview,setPreview]=useState(false);
  const [fitArea,setFitArea]=useState({width:800,height:300});
  const [src,setSrc]=useState(''),[error,setError]=useState(''),[size,setSize]=useState({width:0,height:0});
  const initialPayload=useRef(payload);
  const gesture=useRef<{pointer:number;mode:string;start:{x:number;y:number};before:ImageCrop;rect:DOMRect}|null>(null);
  useEffect(()=>{dialog.current?.showModal()},[]);
  useEffect(()=>{if(!scroll.current)return;const element=scroll.current;const observer=new ResizeObserver(()=>setFitArea({width:element.clientWidth-26,height:window.innerHeight*.42}));observer.observe(element);return()=>observer.disconnect()},[src]);
  useEffect(()=>{
    const controller=new AbortController();let url='';
    void apiFetch(`/api/images/${imageId}/exports/report`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...initialPayload.current as object,crop:null}),signal:controller.signal})
      .then(async response=>{if(!response.ok)throw new Error('Could not prepare the crop preview. Close and try again.');const blob=await response.blob();if(controller.signal.aborted)return;url=URL.createObjectURL(blob);setSrc(url)})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message)});
    return()=>{controller.abort();if(url)URL.revokeObjectURL(url)};
  },[imageId]);
  const point=(event:React.PointerEvent,rect:DOMRect)=>({x:clamp((event.clientX-rect.left)/rect.width,0,1),y:clamp((event.clientY-rect.top)/rect.height,0,1)});
  function begin(event:React.PointerEvent,mode:string){
    if(preview||event.button!==0||!surface.current)return;
    event.preventDefault();event.stopPropagation();event.currentTarget.setPointerCapture(event.pointerId);
    const rect=surface.current.getBoundingClientRect();gesture.current={pointer:event.pointerId,mode,start:point(event,rect),before:selection,rect};
  }
  function move(event:React.PointerEvent){
    const current=gesture.current;if(!current||current.pointer!==event.pointerId)return;
    const end=point(event,current.rect),{before,start,mode}=current;
    if(mode==='move'){setSelection({...before,x:clamp(before.x+end.x-start.x,0,1-before.width),y:clamp(before.y+end.y-start.y,0,1-before.height)});return}
    if(mode==='draw'){setSelection(cropFromPoints(start,end));return}
    const anchor={x:mode.includes('w')?before.x+before.width:before.x,y:mode.includes('n')?before.y+before.height:before.y};
    setSelection(cropFromPoints(anchor,end));
  }
  function change(field:keyof ImageCrop,value:number){
    if(!Number.isFinite(value))return;
    const next={...selection};
    if(field==='x')next.x=clamp(value,0,1-next.width);
    if(field==='y')next.y=clamp(value,0,1-next.height);
    if(field==='width')next.width=clamp(value,.01,1-next.x);
    if(field==='height')next.height=clamp(value,.01,1-next.y);
    setSelection(next);
  }
  const pixels={width:Math.ceil((selection.x+selection.width)*size.width)-Math.floor(selection.x*size.width),height:Math.ceil((selection.y+selection.height)*size.height)-Math.floor(selection.y*size.height)};
  return <dialog ref={dialog} className="cropDialog" aria-labelledby="crop-title" onCancel={event=>{event.preventDefault();onClose()}} onKeyDown={event=>event.stopPropagation()}>
    <header><div><h2 id="crop-title">Crop thermal image</h2><p>Drag a new box, move it, or resize its corner handles.</p></div><button className="ghost" onClick={onClose} aria-label="Close crop editor">✕</button></header>
    {error?<p role="alert" className="authError">{error}</p>:!src?<p role="status">Preparing image with your annotations…</p>:<>
      <div className="cropControls"><label>Selection zoom <input aria-label="Crop selection zoom" type="range" min="100" max="300" step="25" value={zoom} disabled={preview} onChange={e=>setZoom(Number(e.target.value))}/>{zoom}%</label><button className="ghost" onClick={()=>setPreview(!preview)}>{preview?'Edit selection':'Preview crop'}</button><button className="ghost" onClick={()=>{setSelection(full);setPreview(false)}}>Select full image</button></div>
      <div className="cropScroll" ref={scroll}>
        {preview?<div className="cropPreview" style={{width:Math.min(fitArea.width,fitArea.height*size.width*selection.width/(size.height*selection.height)),aspectRatio:`${size.width*selection.width}/${size.height*selection.height}`}}><img src={src} alt="Cropped report preview" style={{width:`${100/selection.width}%`,transform:`translate(${-selection.x*100}%,${-selection.y*100}%)`}}/></div>:
        <div ref={surface} className="cropSurface" style={{width:Math.min(fitArea.width,fitArea.height*(size.width||640)/(size.height||512))*zoom/100}} onPointerDown={e=>begin(e,'draw')} onPointerMove={move} onPointerUp={()=>{gesture.current=null}} onPointerCancel={()=>{gesture.current=null}}>
          <img src={src} alt="Select part of the thermal image to crop" draggable={false} onLoad={e=>setSize({width:e.currentTarget.naturalWidth,height:e.currentTarget.naturalHeight})}/>
          <div className="cropSelection" style={{left:`${selection.x*100}%`,top:`${selection.y*100}%`,width:`${selection.width*100}%`,height:`${selection.height*100}%`}} onPointerDown={e=>begin(e,'move')}>
            <div className="cropGrid"/>{['nw','ne','sw','se'].map(corner=><span key={corner} className={`cropHandle ${corner}`} onPointerDown={e=>begin(e,corner)}/>)}
          </div>
        </div>}
      </div>
      <div className="cropFields">{(['x','y','width','height'] as const).map(field=><label key={field}>{({x:'Left',y:'Top',width:'Width',height:'Height'})[field]} %<input type="number" aria-label={`Crop ${field} percent`} min={field==='width'||field==='height'?1:0} max="100" step="0.1" value={Math.round(selection[field]*1000)/10} onChange={e=>change(field,Number(e.target.value)/100)}/></label>)}<strong>{pixels.width} × {pixels.height} px</strong></div>
    </>}
    <p className="cropExplanation">Report PNGs and Save back to inspection use this crop, including annotations inside it. Measurements still refer to the original image or selected region. Draw a region to measure just the cropped area. The original image and temperature data stay available.</p>
    <footer><button className="ghost" onClick={onClose}>Cancel</button>{crop&&<button className="ghost" onClick={()=>onApply(null)}>Restore full image</button>}<button className="primary" disabled={!src||!!error||!size.width} onClick={()=>onApply(selection.x===0&&selection.y===0&&selection.width===1&&selection.height===1?null:selection)}>Apply crop</button></footer>
  </dialog>;
}
