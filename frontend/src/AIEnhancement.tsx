import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,Send,Sparkles,Undo2,X} from 'lucide-react';
import {api} from './api';
import type {EnhancementController,EnhancementSettings} from './ImageEnhancement';
import './ai-enhancement.css';
import FocusOutlineEditor from './FocusOutlineEditor';
import {newFocus,type FocusPoint} from './InsulatorFocus';

type Turn={role:'user'|'assistant';text:string};
type Proposal={message:string;settings:EnhancementSettings|null};
type ImageInput={id:number;name:string;preview_url:string};
export default function AIEnhancement({image,control:c}:{image?:ImageInput;control:EnhancementController}){
 const [drawing,setDrawing]=useState(false);
 const [open,setOpen]=useState(false),[available,setAvailable]=useState<boolean|null>(null);
 const [messages,setMessages]=useState<Turn[]>([]),[prompt,setPrompt]=useState(''),[error,setError]=useState('');
 const [busy,setBusy]=useState(false),[proposal,setProposal]=useState<EnhancementSettings|null>(null);
 const [preview,setPreview]=useState(''),[compare,setCompare]=useState(false),[outline,setOutline]=useState(true);
 const [base,setBase]=useState(''),[applied,setApplied]=useState(false);
 const request=useRef<AbortController|null>(null),dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const bottom=useRef<HTMLDivElement>(null);
 const current=JSON.stringify(c.settings);
 const stale=!!base&&base!==current;
 useEffect(()=>()=>request.current?.abort(),[]);
 useEffect(()=>{if(!open)return;dialog.current?.showModal();const controller=new AbortController();
  setAvailable(null);api<{available:boolean}>('/api/ai-enhancement/status',{signal:controller.signal}).then(v=>setAvailable(v.available)).catch(e=>{if(!controller.signal.aborted)setError(e.message)});
  return()=>controller.abort();
 },[open]);
 useEffect(()=>{bottom.current?.scrollIntoView({block:'nearest'})},[messages,busy]);
 const close=()=>{request.current?.abort();setBusy(false);setDrawing(false);setOpen(false);trigger.current?.focus()};
 const manual=()=>{setDrawing(true);setError('');setApplied(false);setProposal(null);setPreview('');setBase('')};
 const previewFocus=async(points:FocusPoint[])=>{
  if(!image)return;
  const controller=new AbortController();request.current=controller;setBusy(true);setError('');setApplied(false);
  const next:EnhancementSettings={...c.settings,focus:{...newFocus(points,c.settings.focus),background_dim:1,background_mode:'blue',clarity:0,detail:0,shadows:0},concealed_areas:[]};
  try{
   const rendered=await api<{preview:string}>(`/api/images/${image.id}/enhancement/preview`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:next,analysis_id:c.analysis?.status==='completed'?c.analysis.id:null})});
   if(controller.signal.aborted)return;
   setProposal(next);setPreview(rendered.preview);setBase(current);setCompare(false);setDrawing(false);
  }catch(e:any){if(!controller.signal.aborted)setError(e.message)}finally{if(!controller.signal.aborted)setBusy(false)}
 };
 const send=async()=>{
  if(!image||!prompt.trim()||busy||!available)return;
  const controller=new AbortController();request.current=controller;
  const question=prompt.trim(),seed=proposal&&!stale?proposal:c.settings;
  const history=[...messages,{role:'user' as const,text:question}];
  setMessages(history);setPrompt('');setError('');setBusy(true);setApplied(false);setDrawing(false);
  try{
   const answer=await api<Proposal>(`/api/images/${image.id}/enhancement/ai`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:question,history:messages.slice(-12),settings:seed,analysis_id:c.analysis?.status==='completed'?c.analysis.id:null})});
   if(controller.signal.aborted)return;
   setMessages([...history,{role:'assistant',text:answer.message}]);
   if(answer.settings){
    const rendered=await api<{preview:string}>(`/api/images/${image.id}/enhancement/preview`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:answer.settings,analysis_id:c.analysis?.status==='completed'?c.analysis.id:null})});
    if(controller.signal.aborted)return;
    setProposal(answer.settings);setPreview(rendered.preview);setBase(current);setCompare(false);
   }
  }catch(e:any){if(!controller.signal.aborted){setError(e.message);setPrompt(question)}}
  finally{if(!controller.signal.aborted)setBusy(false)}
 };
 const apply=()=>{if(!proposal||stale)return;c.endGesture();c.change(proposal);c.setFocusOutline(false);setProposal(null);setPreview('');setBase('');setApplied(true);setDrawing(false);setMessages(v=>[...v,{role:'assistant',text:'Applied to your workspace. Save draft to keep it, or export the report image. You can undo this adjustment.'}])};
 return <><button ref={trigger} type="button" className="select aiEnhanceTrigger" disabled={!image||!c.ready} aria-haspopup="dialog" onClick={()=>{setError('');setOpen(true)}}><Sparkles size={16}/> AI Enhancement</button>
 {open&&image&&createPortal(<dialog ref={dialog} className="aiEnhanceDialog" aria-labelledby="ai-enhance-title" onKeyDown={e=>e.stopPropagation()} onCancel={e=>{e.preventDefault();close()}}>
  <header><div><span className="aiEyebrow">ASSISTED DISPLAY EDITING</span><h2 id="ai-enhance-title"><Sparkles/> AI Enhancement</h2><p>{image.name}</p></div><button type="button" aria-label="Close AI enhancement" onClick={close}><X/></button></header>
  <div className="aiEnhanceBody"><section className="aiConversation" aria-label="Enhancement conversation">
   <div className="aiDirectFocus"><b>Suppress background heat colors</b><p>Keep mountains, clouds and the tower visible in muted blue. Preserve the insulator’s thermal colors. Works without AI.</p><button type="button" className="primary" disabled={busy} onClick={manual}>1. Outline the insulator to keep</button>{c.settings.focus&&<button type="button" disabled={busy} onClick={()=>void previewFocus(c.settings.focus!.points)}>Use my existing focus area</button>}<ol><li>Outline what you want to keep.</li><li>Preview the blue background.</li><li>Apply, then save your image.</li></ol></div>
   {available===false&&<div className="aiConnection" role="status"><strong>AI chat is not connected</strong><p>Choosing a suggested phrase does not edit the image. Chat needs a server API key. Use <b>Outline the insulator to keep</b> above to make your edit now.</p></div>}
   {available===true&&messages.length===0&&<div className="aiSuggestions">{['Keep the scene visible but suppress background heat colors in blue. Preserve the insulator.','Dim the background and gently enhance the insulator.','Make only the mountains muted blue; preserve the tower and insulator colors.'].map(text=><button key={text} type="button" onClick={()=>setPrompt(text)}>{text}</button>)}</div>}
   {available===true&&<><div className="aiMessages" role="log" aria-live="polite">{messages.map((m,i)=><div key={i} className={`aiMessage ${m.role}`}><b>{m.role==='user'?'You':'AI assistant'}</b><p>{m.text}</p></div>)}{busy&&<p role="status" className="aiWorking">Reading your request and preparing a preview…</p>}<div ref={bottom}/></div>
   <form onSubmit={e=>{e.preventDefault();void send()}}><label htmlFor="ai-instruction">What would you like to change?</label><textarea id="ai-instruction" value={prompt} maxLength={2000} rows={3} onChange={e=>setPrompt(e.target.value)} placeholder="For example: keep insulator colors and make the surrounding scene muted blue…"/><div><button type="button" onClick={manual} disabled={busy}>Draw target manually</button><button className="primary" disabled={busy||!available||prompt.trim().length<3} type="submit"><Send size={15}/>{busy?'Working…':'Preview edit'}</button></div></form>
   <small className="aiPrivacy">Sending shares this image’s visual preview and your prompt with OpenAI. The original radiometric file and temperature matrix stay on this server.</small></>}
  </section><section className="aiReview" aria-label="Review enhancement proposal">
   <div className="aiPreviewHead"><strong>{drawing?'1. Outline your insulator':preview?(compare?'Current workspace':'Proposed edit'):'Current workspace'}</strong>{preview&&<button type="button" aria-pressed={compare} onClick={()=>setCompare(!compare)}>{compare?'Show proposal':'Compare current'}</button>}</div>
   {drawing?<FocusOutlineEditor src={image.preview_url} busy={busy} onPreview={points=>void previewFocus(points)} onCancel={()=>setDrawing(false)}/>:<><div className="aiPreviewImage"><div><img src={preview&&!compare?preview:c.src||image.preview_url} alt={preview&&!compare?'Proposed display edit':'Current thermal display'}/>{preview&&!compare&&outline&&proposal&&<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Proposed mask outlines">{proposal.focus&&<polygon className="keepArea" points={proposal.focus.points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>} {proposal.concealed_areas?.map((area,i)=><polygon key={i} className="hideArea" points={area.points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>)}</svg>}</div></div>
   {preview&&<label className="aiOutline"><input type="checkbox" checked={outline} onChange={e=>setOutline(e.target.checked)}/>Show outlines · cyan preserves thermal colors, red suppresses background</label>}
   <p className="aiReviewHint">{applied?'Your changes are applied. Use Done below to return and save.':preview?'Preview only — click Apply changes below to update your image. Suppressed background colors are for presentation, not temperature readings.':'No new changes yet. Outline your insulator to create a preview.'}</p></>}
   <div className="aiMeasurementNote"><Check size={17}/><div><b>Temperature data preserved</b><p>Blue is a display effect, not zero temperature or a correction to the sensor readings. MAX, MIN and AVG still include background pixels unless you draw a measurement region around the insulator.</p></div></div>
  </section></div>
  <footer className="aiApplyBar">
   {error&&<p className="aiError" role="alert">{error}</p>}
   {stale&&<p className="aiError">The workspace changed. Send your request again to prepare a fresh proposal.</p>}
   {applied&&<p role="status" className="aiApplied">Changes applied to your image. Click Done, then Save draft or Save to inspection to keep them.</p>}
   <div className="aiReviewActions"><button type="button" disabled={busy||!c.undoCount} onClick={()=>{c.undo();setDrawing(false);setApplied(false);setProposal(null);setPreview('');setBase('')}}><Undo2 size={16}/> Undo enhancement</button><button type="button" className="primary" disabled={busy||drawing||!proposal||stale||!c.ready} onClick={apply}><Check size={16}/> 3. Apply changes</button></div>
   {!proposal&&!applied&&<p className="aiApplyHint">{drawing?'Finish the outline and preview it first.':'Apply becomes available after you prepare a preview.'}</p>}
   {applied&&<button type="button" className="primary" onClick={close}>Done — return to image</button>}
   {proposal&&<button type="button" className="aiDiscard" disabled={busy} onClick={()=>{setProposal(null);setPreview('');setBase('')}}>Discard proposal</button>}
  </footer>
 </dialog>,document.body)}</>;
}
