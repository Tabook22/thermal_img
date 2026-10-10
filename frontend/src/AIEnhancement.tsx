import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,Send,Sparkles,Undo2,X} from 'lucide-react';
import {api} from './api';
import type {EnhancementController,EnhancementSettings} from './ImageEnhancement';
import './ai-enhancement.css';

type Turn={role:'user'|'assistant';text:string};
type Proposal={message:string;settings:EnhancementSettings|null};
type ImageInput={id:number;name:string;preview_url:string};
export default function AIEnhancement({image,control:c}:{image?:ImageInput;control:EnhancementController}){
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
 const close=()=>{request.current?.abort();setBusy(false);setOpen(false);trigger.current?.focus()};
 const manual=()=>{close();c.setOpen(true);c.setFocusMode('freehand');c.setSelectingFocus(true)};
 const send=async()=>{
  if(!image||!prompt.trim()||busy||!available)return;
  const controller=new AbortController();request.current=controller;
  const question=prompt.trim(),seed=proposal&&!stale?proposal:c.settings;
  const history=[...messages,{role:'user' as const,text:question}];
  setMessages(history);setPrompt('');setError('');setBusy(true);setApplied(false);
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
 const apply=()=>{if(!proposal||stale)return;c.endGesture();c.change(proposal);c.setFocusOutline(false);setProposal(null);setPreview('');setBase('');setApplied(true);setMessages(v=>[...v,{role:'assistant',text:'Applied to your workspace. Save draft to keep it, or export the report image. You can undo this adjustment.'}])};
 return <><button ref={trigger} type="button" className="select aiEnhanceTrigger" disabled={!image||!c.ready} aria-haspopup="dialog" onClick={()=>{setError('');setOpen(true)}}><Sparkles size={16}/> AI Enhancement</button>
 {open&&image&&createPortal(<dialog ref={dialog} className="aiEnhanceDialog" aria-labelledby="ai-enhance-title" onKeyDown={e=>e.stopPropagation()} onCancel={e=>{e.preventDefault();close()}}>
  <header><div><span className="aiEyebrow">ASSISTED DISPLAY EDITING</span><h2 id="ai-enhance-title"><Sparkles/> AI Enhancement</h2><p>{image.name}</p></div><button type="button" aria-label="Close AI enhancement" onClick={close}><X/></button></header>
  <div className="aiEnhanceBody"><section className="aiConversation" aria-label="Enhancement conversation">
   <p>Tell me what should stand out. Hide a distracting background, isolate an insulator, or bring out captured detail.</p>
   {available===false&&<div className="aiConnection" role="status"><strong>AI connection needed</strong><p>Your administrator needs to configure the server’s OpenAI API key. Manual focus and enhancement are available now.</p><button type="button" onClick={manual}>Draw a focus area instead</button></div>}
   {messages.length===0&&<div className="aiSuggestions">{['Keep only the insulator. Hide the mountains and tower.','Dim the background and gently enhance the insulator.','Hide only the mountains; keep the tower and insulator.'].map(text=><button key={text} type="button" onClick={()=>setPrompt(text)}>{text}</button>)}</div>}
   <div className="aiMessages" role="log" aria-live="polite">{messages.map((m,i)=><div key={i} className={`aiMessage ${m.role}`}><b>{m.role==='user'?'You':'AI assistant'}</b><p>{m.text}</p></div>)}{busy&&<p role="status" className="aiWorking">Reading your request and preparing a preview…</p>}<div ref={bottom}/></div>
   {error&&<p className="aiError" role="alert">{error}</p>}
   <form onSubmit={e=>{e.preventDefault();void send()}}><label htmlFor="ai-instruction">What would you like to change?</label><textarea id="ai-instruction" value={prompt} maxLength={2000} rows={3} onChange={e=>setPrompt(e.target.value)} placeholder="For example: keep the central insulator and hide everything behind it…"/><div><button type="button" onClick={manual} disabled={busy}>Draw target manually</button><button className="primary" disabled={busy||!available||prompt.trim().length<3} type="submit"><Send size={15}/>{busy?'Working…':'Preview edit'}</button></div></form>
   <small className="aiPrivacy">Sending shares this image’s visual preview and your prompt with OpenAI. The original radiometric file and temperature matrix stay on this server.</small>
  </section><section className="aiReview" aria-label="Review enhancement proposal">
   <div className="aiPreviewHead"><strong>{preview?(compare?'Current workspace':'Proposed edit'):'Current workspace'}</strong>{preview&&<button type="button" aria-pressed={compare} onClick={()=>setCompare(!compare)}>{compare?'Show proposal':'Compare current'}</button>}</div>
   <div className="aiPreviewImage"><div><img src={preview&&!compare?preview:c.src||image.preview_url} alt={preview&&!compare?'Proposed AI display edit':'Current thermal display'}/>{preview&&!compare&&outline&&proposal&&<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Proposed mask outlines">{proposal.focus&&<polygon className="keepArea" points={proposal.focus.points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>} {proposal.concealed_areas?.map((area,i)=><polygon key={i} className="hideArea" points={area.points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>)}</svg>}</div></div>
   {preview&&<label className="aiOutline"><input type="checkbox" checked={outline} onChange={e=>setOutline(e.target.checked)}/>Show proposed outlines · cyan keeps, red hides</label>}
   <p className="aiReviewHint">Review the edges before applying. AI outlines are approximate; you can refine the focus manually. Hidden areas are shown in black, not reconstructed.</p>
   <div className="aiMeasurementNote"><Check size={17}/><div><b>Temperature data preserved</b><p>Edits change the display only. MAX, MIN and AVG still refer to the original measurement area, including hidden pixels. Draw a measurement region for insulator-only readings.</p></div></div>
   {stale&&<p className="aiError">The workspace changed. Send your request again to prepare a fresh proposal.</p>}
   {applied&&<p role="status" className="aiApplied">Applied. Save draft or export when ready.</p>}
   <div className="aiReviewActions"><button type="button" disabled={busy||!c.undoCount} onClick={()=>{c.undo();setApplied(false);setProposal(null);setPreview('');setBase('')}}><Undo2 size={16}/> Undo enhancement</button><button type="button" className="primary" disabled={busy||!proposal||stale||!c.ready} onClick={apply}><Check size={16}/> Apply to image</button></div>
   {proposal&&<button type="button" className="aiDiscard" disabled={busy} onClick={()=>{setProposal(null);setPreview('');setBase('')}}>Discard proposal</button>}
  </section></div>
 </dialog>,document.body)}</>;
}
