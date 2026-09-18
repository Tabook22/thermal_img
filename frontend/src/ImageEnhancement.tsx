import {useEffect,useLayoutEffect,useRef,useState,type PointerEvent as ReactPointerEvent} from 'react';
import {createPortal} from 'react-dom';
import {Check,Eye,RotateCcw,Save,SlidersHorizontal,Sparkles,Redo2,Undo2,X} from 'lucide-react';
import {api,type Analysis} from './api';
import './image-enhancement.css';
import {InsulatorFocusControls,type InsulatorFocus,type FocusRegion} from './InsulatorFocus';

type Palette='original'|'iron'|'inferno'|'arctic'|'gray';
export type EnhancementSettings={palette:Palette;low:number|null;high:number|null;brightness:number;contrast:number;gamma:number;saturation:number;local_contrast:number;denoise:number;sharpen:number;red:number;yellow:number;green:number;cyan:number;blue:number;purple:number;highlight:boolean;highlight_low:number|null;highlight_high:number|null;focus:InsulatorFocus|null};
const defaults:EnhancementSettings={palette:'original',low:null,high:null,brightness:0,contrast:1,gamma:1,saturation:1,local_contrast:0,denoise:0,sharpen:0,red:1,yellow:1,green:1,cyan:1,blue:1,purple:1,highlight:false,highlight_low:null,highlight_high:null,focus:null};
type Preview={preview:string;low:number|null;high:number|null;legend:string[];quantitative_legend:boolean;width:number;height:number;focus_info:{warning:string|null;bounds:number[];pixels:number}|null};
type ImageInput={id:number;preview_url:string};
const key=(value:EnhancementSettings)=>JSON.stringify(value);

export function useImageEnhancement(image:ImageInput|undefined,analysis:Analysis|undefined){
 const [settings,setSettings]=useState<EnhancementSettings>(defaults);
 const [selectingFocus,setSelectingFocus]=useState(false),[focusOutline,setFocusOutline]=useState(true),[focusCompare,setFocusCompare]=useState(false);
 const settingsRef=useRef(settings);
 const [savedKey,setSavedKey]=useState(key(defaults));
 const [readyId,setReadyId]=useState<number>();
 const [loadAttempt,setLoadAttempt]=useState(0);
 const [rendered,setRendered]=useState<{imageId:number;result:Preview}|null>(null);
 const [open,setOpen]=useState(false),[comparison,setComparison]=useState(false),[split,setSplit]=useState(50),[showOriginal,setShowOriginal]=useState(false);
 const [processing,setProcessing]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [undoCount,setUndoCount]=useState(0),[redoCount,setRedoCount]=useState(0);
 const future=useRef<EnhancementSettings[]>([]),gestureRecorded=useRef(false);
 const [focusMode,setFocusMode]=useState<'box'|'freehand'>('box');
 const history=useRef<EnhancementSettings[]>([]),grouping=useRef(false);
 const activeId=useRef(image?.id);activeId.current=image?.id;
 const analysisId=analysis?.status==='completed'?analysis.id:undefined;
 const ready=!!image&&readyId===image.id;
 useEffect(()=>{
  setSelectingFocus(false);setFocusCompare(false);setReadyId(undefined);setRendered(null);setComparison(false);setShowOriginal(false);setSettings(defaults);settingsRef.current=defaults;setSavedKey(key(defaults));setError('');setBusy(false);setProcessing(false);history.current=[];future.current=[];setRedoCount(0);grouping.current=false;setUndoCount(0);
  if(!image)return;
  const controller=new AbortController();
  api<EnhancementSettings>(`/api/images/${image.id}/enhancement`,{signal:controller.signal}).then(value=>{if(controller.signal.aborted)return;const loaded={...defaults,...value};settingsRef.current=loaded;setSettings(loaded);setSavedKey(key(loaded));setReadyId(image.id)}).catch(cause=>{if(!controller.signal.aborted)setError(cause.message)});
  return()=>controller.abort();
 },[image?.id,loadAttempt]);
 useEffect(()=>{
  if(!image||!ready)return;
  const controller=new AbortController();
  if(key(settings)===key(defaults)){setRendered(null);setProcessing(false);return}
  setProcessing(true);
  const timer=setTimeout(()=>{
   api<Preview>(`/api/images/${image.id}/enhancement/preview`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({settings,analysis_id:analysisId})}).then(result=>{if(!controller.signal.aborted){setRendered({imageId:image.id,result});setError('')}}).catch(cause=>{if(!controller.signal.aborted)setError(cause.message)}).finally(()=>{if(!controller.signal.aborted)setProcessing(false)});
  },200);
  return()=>{clearTimeout(timer);controller.abort()};
 },[image?.id,ready,settings,analysisId]);
 useEffect(()=>{if(!open)setSelectingFocus(false)},[open]);
 useEffect(()=>{if(!selectingFocus)return;const cancel=(event:KeyboardEvent)=>{if(event.key==='Escape')setSelectingFocus(false)};window.addEventListener('keydown',cancel);return()=>window.removeEventListener('keydown',cancel)},[selectingFocus]);
 const remember=()=>{history.current=[...history.current.slice(-29),settingsRef.current];setUndoCount(history.current.length)};
 const change=(patch:Partial<EnhancementSettings>)=>{const next={...settingsRef.current,...patch};if(key(next)===key(settingsRef.current))return;if(!grouping.current||!gestureRecorded.current){remember();gestureRecorded.current=true}future.current=[];setRedoCount(0);settingsRef.current=next;setSettings(next);setShowOriginal(false);setError('')};
 const beginGesture=()=>{if(!grouping.current){gestureRecorded.current=false;grouping.current=true}};
 const endGesture=()=>{grouping.current=false};
 const undo=()=>{const last=history.current.pop();if(last){future.current.push(settingsRef.current);setRedoCount(future.current.length);settingsRef.current=last;setSettings(last);setUndoCount(history.current.length);setError('')}};
 const redo=()=>{const next=future.current.pop();if(next){remember();settingsRef.current=next;setSettings(next);setRedoCount(future.current.length);setError('')}};
 const reset=()=>{change(defaults);setComparison(false);setSelectingFocus(false);setFocusCompare(false)};
 const save=async()=>{if(!image||!ready)return;const id=image.id,value=settingsRef.current;setBusy(true);setError('');try{await api(`/api/images/${id}/enhancement`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});if(activeId.current===id)setSavedKey(key(value))}catch(cause:any){if(activeId.current===id)setError(cause.message)}finally{if(activeId.current===id)setBusy(false)}};
 const auto=async()=>{if(!image||!ready)return;const id=image.id;setBusy(true);setError('');try{const value=await api<EnhancementSettings>(`/api/images/${id}/enhancement/auto`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({analysis_id:analysisId})});if(activeId.current===id)change({...value,focus:settingsRef.current.focus})}catch(cause:any){if(activeId.current===id)setError(cause.message)}finally{if(activeId.current===id)setBusy(false)}};
 const preview=rendered?.imageId===image?.id?rendered?.result:undefined;
 return {focusMode,setFocusMode,redo,redoCount,originalSrc:image?.preview_url,selectingFocus,setSelectingFocus,focusOutline,setFocusOutline,focusCompare,setFocusCompare,settings,ready,open,setOpen,comparison,setComparison,split,setSplit,showOriginal,setShowOriginal,processing,busy,error,undoCount,undo,reset,save,auto,change,beginGesture,endGesture,retry:()=>setLoadAttempt(value=>value+1),dirty:key(settings)!==savedKey,preview,src:showOriginal?image?.preview_url:preview?.preview||image?.preview_url,analysis};
}

export type EnhancementController=ReturnType<typeof useImageEnhancement>;
export function EnhancementPanel({control:c,regions=[]}:{control:EnhancementController;regions?:FocusRegion[]}){
 if(!c.open)return null;
 const s=c.settings,stats=c.analysis?.statistics,thermal=c.analysis?.status==='completed';
 const min=stats?.minimum_c??0,max=Math.max(min+.1,stats?.maximum_c??100);
 const low=s.low??min,high=s.high??max;
 const slider=(label:string,name:keyof EnhancementSettings,start:number,end:number,step:number,suffix='%')=><label className="enhanceSlider"><span>{label}<output>{suffix==='%'?Math.round(Number(s[name])*100):Number(s[name]).toFixed(name==='brightness'?0:2)}{suffix}</output></span><input type="range" aria-label={label} min={start} max={end} step={step} value={Number(s[name])} onPointerDown={c.beginGesture} onPointerUp={c.endGesture} onPointerCancel={c.endGesture} onLostPointerCapture={c.endGesture} onChange={e=>c.change({[name]:Number(e.target.value)})}/></label>;
 return <section className="enhancePanel" aria-label="Image enhancement">
  <div className="enhanceHead"><div><SlidersHorizontal size={17}/><strong>Enhance image</strong></div><button type="button" aria-label="Close enhancement panel" onClick={()=>c.setOpen(false)}><X size={18}/></button></div>
  <p className="enhanceIntro">Reveal detail. Keep the original measurements.</p>
  <div className="enhanceQuick"><button type="button" disabled={!c.ready||c.busy} onClick={()=>void c.auto()}><Sparkles size={15}/>{c.busy?'Working…':'Auto enhance'}</button><button type="button" aria-pressed={c.showOriginal} onClick={()=>c.setShowOriginal(!c.showOriginal)}><Eye size={15}/>{c.showOriginal?'Show enhanced':'Show original'}</button></div>
  <p className="enhanceHint">Auto adjusts contrast and detail locally on this computer.</p>
  <fieldset disabled={!c.ready||c.busy} className="enhanceBody">
   <InsulatorFocusControls control={c} regions={regions}/>
   <label className="enhanceSelect">Palette<select value={s.palette} onChange={e=>c.change({palette:e.target.value as Palette})}><option value="original">Original image colors</option><option disabled={!thermal} value="iron">Iron</option><option disabled={!thermal} value="inferno">Inferno</option><option disabled={!thermal} value="arctic">Arctic</option><option disabled={!thermal} value="gray">Grayscale</option></select></label>
   {!thermal&&<p className="enhanceHint">Complete a radiometric analysis to enable temperature palettes and highlighting.</p>}
   {thermal&&<div className="enhanceRange"><div className="enhanceSectionLabel">Display temperature range <span>°C</span></div><p className="enhanceHint">Choose a thermal palette to adjust its temperature scale.</p><div><label>Low<input aria-label="Display minimum temperature" type="number" step="0.1" disabled={s.palette==='original'} value={Number(low.toFixed(2))} onFocus={c.beginGesture} onBlur={c.endGesture} onChange={e=>{if(e.target.value)c.change({low:Math.min(high-.01,Number(e.target.value)),high})}}/></label><label>High<input aria-label="Display maximum temperature" type="number" step="0.1" disabled={s.palette==='original'} value={Number(high.toFixed(2))} onFocus={c.beginGesture} onBlur={c.endGesture} onChange={e=>{if(e.target.value)c.change({low,high:Math.max(low+.01,Number(e.target.value))})}}/></label><button type="button" disabled={s.palette==='original'} onClick={()=>c.change({low:null,high:null})}>Full range</button></div></div>}
   <details open><summary>Light & contrast</summary>{slider('Brightness','brightness',-50,50,1,'')}{slider('Contrast','contrast',.5,2,.01)}{slider('Midtones (gamma)','gamma',.4,2.5,.01,'×')}{slider('Color saturation','saturation',0,2,.01)}</details>
   <details><summary>Detail & noise</summary>{slider('Local contrast','local_contrast',0,1,.01)}{slider('Noise reduction','denoise',0,1,.01)}{slider('Sharpening','sharpen',0,1,.01)}<p className="enhanceHint">Use gently. Enhancement cannot recover missing temperature data or correct a poorly focused capture.</p></details>
   <details><summary>Individual colors</summary><p className="enhanceHint">0% removes a color’s saturation; 100% keeps it; 200% strengthens it.</p>{(['red','yellow','green','cyan','blue','purple'] as const).map(name=><div key={name} className={`enhanceColor ${name}`}>{slider(name[0].toUpperCase()+name.slice(1),name,0,2,.01)}</div>)}</details>
   {thermal&&<details><summary>Highlight temperatures</summary><label className="enhanceCheck"><input type="checkbox" checked={s.highlight} onChange={e=>c.change({highlight:e.target.checked,highlight_low:s.highlight_low??(min+(max-min)*.75),highlight_high:s.highlight_high??max})}/>Dim pixels outside this band</label>{s.highlight&&<div className="enhanceRange"><div><label>From °C<input aria-label="Highlight minimum temperature" type="number" step="0.1" value={Number(s.highlight_low?.toFixed(2))} onChange={e=>{if(e.target.value)c.change({highlight_low:Math.min(s.highlight_high!-.01,Number(e.target.value))})}}/></label><label>To °C<input aria-label="Highlight maximum temperature" type="number" step="0.1" value={Number(s.highlight_high?.toFixed(2))} onChange={e=>{if(e.target.value)c.change({highlight_high:Math.max(s.highlight_low!+.01,Number(e.target.value))})}}/></label></div></div>}</details>}
   <div className="enhanceCompare"><label className="enhanceCheck"><input type="checkbox" checked={c.comparison} onChange={e=>{c.setComparison(e.target.checked);c.setShowOriginal(false)}}/>Compare original / enhanced</label>{c.comparison&&<label className="enhanceSlider"><span>Comparison divider<output>{c.split}%</output></span><input type="range" aria-label="Comparison divider" min="0" max="100" value={c.split} onChange={e=>c.setSplit(Number(e.target.value))}/></label>}</div>
  </fieldset>
  {c.error&&<p className="enhanceError" role="alert">{c.error}{!c.ready&&<button type="button" onClick={c.retry}>Retry loading settings</button>}</p>}
  <div className="enhanceFooter"><div><button type="button" disabled={!c.undoCount||c.busy} onClick={c.undo} title="Undo enhancement"><Undo2 size={15}/>Undo</button><button type="button" disabled={!c.redoCount||c.busy} onClick={c.redo} title="Redo enhancement"><Redo2 size={15}/>Redo</button><button type="button" disabled={!c.ready||c.busy} onClick={c.reset}><RotateCcw size={15}/>Reset</button><button type="button" className="enhanceSave" disabled={!c.dirty||!c.ready||c.busy||c.processing} onClick={()=>void c.save()}><Save size={15}/>Save</button></div><span role="status">{c.processing?'Updating preview…':c.showOriginal?'Showing original image':!c.ready?(c.error?'Settings unavailable':'Loading settings…'):c.dirty?'Unsaved display settings':<><Check size={12}/> Settings saved for this image</>}</span></div>
 </section>;
}

export function EnhancementLegend({control:c}:{control:EnhancementController}){
 const p=c.preview;
 const originalColors=['#100a35','#351069','#72217e','#b52a91','#f05857','#ffe27a'];
 const referenceOnly=c.showOriginal||c.settings.palette==='original'||!p?.legend.length;
 const colors=referenceOnly?originalColors:p!.legend;
 const calibrated=!referenceOnly&&p!.quantitative_legend;
 const legendRef=useRef<HTMLDivElement>(null);
 const [position,setPosition]=useState<{x:number;y:number}|null>(null);
 const drag=useRef<{id:number;clientX:number;clientY:number;x:number;y:number}|null>(null);
 useLayoutEffect(()=>{
  if(!c.originalSrc)return;
  const canvas=document.querySelector('.workspace .canvas')?.getBoundingClientRect();
  const width=legendRef.current?.offsetWidth||48,height=legendRef.current?.offsetHeight||220;
  setPosition({x:Math.max(0,Math.min(window.innerWidth-width,canvas?canvas.right-width-18:window.innerWidth-width-18)),y:Math.max(0,Math.min(window.innerHeight-height,canvas?canvas.top+(canvas.height-height)/2:80))});
 },[c.originalSrc]);
 useEffect(()=>{const keepVisible=()=>setPosition(current=>current?{x:Math.max(0,Math.min(current.x,window.innerWidth-(legendRef.current?.offsetWidth||48))),y:Math.max(0,Math.min(current.y,window.innerHeight-(legendRef.current?.offsetHeight||220)))}:null);window.addEventListener('resize',keepVisible);return()=>window.removeEventListener('resize',keepVisible)},[]);
 if(!c.originalSrc)return null;
 const down=(e:ReactPointerEvent<HTMLDivElement>)=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const rect=e.currentTarget.getBoundingClientRect();e.currentTarget.setPointerCapture(e.pointerId);drag.current={id:e.pointerId,clientX:e.clientX,clientY:e.clientY,x:rect.left,y:rect.top}};
 const move=(e:ReactPointerEvent<HTMLDivElement>)=>{const d=drag.current;if(d?.id!==e.pointerId)return;e.preventDefault();const width=legendRef.current?.offsetWidth||48,height=legendRef.current?.offsetHeight||220;setPosition({x:Math.max(0,Math.min(window.innerWidth-width,d.x+e.clientX-d.clientX)),y:Math.max(0,Math.min(window.innerHeight-height,d.y+e.clientY-d.clientY))})};
 const end=(e:ReactPointerEvent<HTMLDivElement>)=>{if(drag.current?.id===e.pointerId)drag.current=null};
 return createPortal(<div ref={legendRef} role="img" aria-label="Draggable thermal color legend" className="colorbar enhancementLegend" style={position?{left:position.x,top:position.y}:undefined} title={calibrated?'Drag the displayed temperature scale anywhere in the app window':'Drag the approximate color guide anywhere in the app window. Colors are not a measured temperature scale.'} onPointerDown={down} onPointerMove={move} onPointerUp={end} onPointerCancel={end}><span>{calibrated?`${p!.high?.toFixed(1)}°C`:'Warm'}</span><div style={{background:`linear-gradient(to top, ${colors.join(',')})`}}/><span>{calibrated?`${p!.low?.toFixed(1)}°C`:'Cool'}</span><small>{calibrated?'Display °C':'Color guide'}</small></div>,document.body);
}
