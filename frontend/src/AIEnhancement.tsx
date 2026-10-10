import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,ImagePlus,Send,Sparkles,Undo2,X} from 'lucide-react';
import {api} from './api';
import type {EnhancementController,EnhancementSettings} from './ImageEnhancement';
import './ai-enhancement.css';
import FocusOutlineEditor from './FocusOutlineEditor';
import {newFocus,type FocusPoint,type FocusStroke} from './InsulatorFocus';

type Turn={role:'user'|'assistant';text:string};
type Proposal={message:string;settings:EnhancementSettings|null};
type ImageInput={id:number;name:string;preview_url:string};
const EXAMPLE_PROMPT='Remove the heat from the background, especially the mountains, sky and tower. Focus only on the heat from the insulator itself. Keep the surrounding scene visible in muted blue and enhance the image for a clear, professional result.';
export default function AIEnhancement({image,control:c,onUpload,uploading=false}:{image?:ImageInput;control:EnhancementController;onUpload:(files:FileList|null)=>Promise<void>;uploading?:boolean}){
 const [drawing,setDrawing]=useState(false);
 const [open,setOpen]=useState(false),[available,setAvailable]=useState<boolean|null>(null);
 const [connection,setConnection]=useState<{provider:string;provider_name:string;model:string}|null>(null);
 const [messages,setMessages]=useState<Turn[]>([]),[prompt,setPrompt]=useState(EXAMPLE_PROMPT),[error,setError]=useState('');
 const [busy,setBusy]=useState(false),[proposal,setProposal]=useState<EnhancementSettings|null>(null);
 const [preview,setPreview]=useState(''),[compare,setCompare]=useState(false),[outline,setOutline]=useState(false);
 const [base,setBase]=useState(''),[applied,setApplied]=useState(false);
 const request=useRef<AbortController|null>(null),dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const bottom=useRef<HTMLDivElement>(null),fileInput=useRef<HTMLInputElement>(null);
 const blocked=busy||uploading||!image||!c.ready;
 const current=JSON.stringify(c.settings);
 const stale=!!base&&base!==current;
 useEffect(()=>()=>request.current?.abort(),[]);
 useEffect(()=>{request.current?.abort();setBusy(false);setDrawing(false);setMessages([]);setPrompt(EXAMPLE_PROMPT);setProposal(null);setPreview('');setBase('');setApplied(false);setCompare(false);setOutline(false);setError('')},[image?.id]);
 useEffect(()=>{if(!open)return;dialog.current?.showModal();const controller=new AbortController();
  setAvailable(null);setConnection(null);api<{available:boolean;provider:string;provider_name:string;model:string}>('/api/ai-enhancement/status',{signal:controller.signal}).then(v=>{setAvailable(v.available);setConnection(v)}).catch(e=>{if(!controller.signal.aborted)setError(e.message)});
  return()=>controller.abort();
 },[open]);
 useEffect(()=>{bottom.current?.scrollIntoView({block:'nearest'})},[messages,busy]);
 const close=()=>{request.current?.abort();setBusy(false);setDrawing(false);setOpen(false);trigger.current?.focus()};
 const manual=()=>{setDrawing(true);setError('');setApplied(false)};
 const previewFocus=async(points:FocusPoint[],strokes:FocusStroke[]=[])=>{
  if(!image)return;
  const controller=new AbortController();request.current=controller;setBusy(true);setError('');setApplied(false);
  const next:EnhancementSettings={...c.settings,focus:{...newFocus(points,c.settings.focus),strokes,preserve_original:true,feather:.001,background_dim:1,background_mode:'blue',clarity:0,detail:0,shadows:0},concealed_areas:[]};
  try{
   const rendered=await api<{preview:string}>(`/api/images/${image.id}/enhancement/preview`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:next,analysis_id:c.analysis?.status==='completed'?c.analysis.id:null})});
   if(controller.signal.aborted)return;
   setProposal(next);setPreview(rendered.preview);setBase(current);setCompare(false);setDrawing(false);
  }catch(e:any){if(!controller.signal.aborted)setError(e.message)}finally{if(!controller.signal.aborted)setBusy(false)}
 };
 const send=async()=>{
  if(blocked||!image||prompt.trim().length<3||!available)return;
  const controller=new AbortController();request.current=controller;
  const question=prompt.trim(),seed=proposal&&!stale?proposal:c.settings;
  const history=[...messages,{role:'user' as const,text:question}];
  setMessages(history);setPrompt('');setError('');setBusy(true);setApplied(false);setDrawing(false);setProposal(null);setPreview('');setBase('');
  try{
   const answer=await api<Proposal>(`/api/images/${image.id}/enhancement/ai`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:connection?.provider,model:connection?.model,prompt:question,history:messages.slice(-12),settings:seed,analysis_id:c.analysis?.status==='completed'?c.analysis.id:null})});
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
 const apply=()=>{if(blocked||!proposal||stale)return;c.endGesture();c.change(proposal);c.setFocusOutline(false);setProposal(null);setPreview('');setBase('');setApplied(true);setDrawing(false);setMessages(v=>[...v,{role:'assistant',text:'Applied to your workspace. Save draft to keep it, or export the report image. You can undo this adjustment.'}])};
 return <><button ref={trigger} type="button" className="select aiEnhanceTrigger" disabled={uploading||!!image&&!c.ready} aria-haspopup="dialog" onClick={()=>{setError('');setOpen(true)}}><Sparkles size={16}/> AI Enhancement</button>
 {open&&createPortal(<dialog ref={dialog} className="aiEnhanceDialog" aria-labelledby="ai-enhance-title" onKeyDown={e=>e.stopPropagation()} onCancel={e=>{e.preventDefault();close()}}>
  <header><div><span className="aiEyebrow">FOCUS ON WHAT MATTERS</span><h2 id="ai-enhance-title"><Sparkles/> AI Enhancement</h2><p>Upload an image. Describe your edit. Let AI prepare the result.</p></div><button type="button" aria-label="Close AI Enhancement" onClick={close}><X/></button></header>
  <div className="aiEnhanceBody"><section className="aiConversation" aria-label="Enhancement conversation">
   <div className="aiImageCard"><div>{image&&<img src={image.preview_url} alt="Selected thermal image"/>}<div><small>{uploading?'UPLOADING…':image?'SELECTED IMAGE':'START WITH AN IMAGE'}</small><strong>{image?.name||'Upload your thermal image'}</strong></div></div><button type="button" disabled={busy||uploading} onClick={()=>fileInput.current?.click()}><ImagePlus size={16}/>{image?'Change image':'Upload image'}</button><input ref={fileInput} type="file" hidden accept="image/jpeg,image/png,.thermalpkg" onChange={e=>{const input=e.currentTarget;void onUpload(input.files).catch(e=>setError(e.message)).finally(()=>{input.value=''})}}/></div>
   {available===null&&!error&&<p role="status">Connecting to AI…</p>}
   {available===false&&<div className="aiConnection" role="status"><strong>Connect AI to get started</strong><p>An administrator can add a provider and API key in Settings → AI connection. Manual controls below remain available.</p></div>}
   {available===true&&connection&&<p className="aiProviderLine"><span/> {connection.provider_name} · {connection.model}</p>}
   <div className="aiMessages" role="log" aria-live="polite">
    {messages.length===0&&<div className="aiWelcome"><Sparkles size={24}/><h3>Keep the insulator’s heat in focus</h3><p>Ask AI to suppress heat colors from mountains, clouds, the tower or other surroundings. No drawing needed to get started.</p></div>}
    {messages.map((m,i)=><div key={i} className={`aiMessage ${m.role}`}><b>{m.role==='user'?'You':'AI assistant'}</b><p>{m.text}</p></div>)}
    {busy&&<p role="status" className="aiWorking"><Sparkles size={15}/> AI is preparing your image…</p>}<div ref={bottom}/>
   </div>
   <form onSubmit={e=>{e.preventDefault();void send()}}><label htmlFor="ai-instruction">{messages.length?'Tell AI what to adjust':'What would you like AI to do?'}</label><textarea id="ai-instruction" value={prompt} maxLength={2000} rows={4} disabled={busy||uploading} onChange={e=>setPrompt(e.target.value)} placeholder="Remove background heat colors and focus on the insulator…"/><div><button type="button" className="aiExample" disabled={busy||uploading} onClick={()=>setPrompt(EXAMPLE_PROMPT)}>Use example prompt</button><button className="primary" disabled={blocked||!available||prompt.trim().length<3} type="submit"><Send size={15}/>{busy?'Enhancing…':messages.length?'Send to AI':'Enhance with AI'}</button></div></form>
   <small className="aiPrivacy">Sending shares the image preview and your message with {connection?.provider_name||'your AI provider'}. Original temperature data stays on this server.</small>
   <details className="aiManualOptions"><summary>Manual controls (optional)</summary><p>Refine the selection if AI misses an edge, or work without AI.</p><button type="button" onClick={manual} disabled={blocked}>Refine selection manually</button>{c.settings.focus&&<button type="button" disabled={blocked} onClick={()=>void previewFocus(c.settings.focus!.points,c.settings.focus!.strokes)}>Use existing focus area</button>}</details>
  </section><section className="aiReview" aria-label="Review enhancement proposal">
   <div className="aiPreviewHead"><strong>{drawing?'Refine selection':preview?(compare?'Before':'AI result'):applied?'Applied result':'Your image'}</strong>{preview&&<div className="aiCompareSwitch" aria-label="Compare images"><button type="button" aria-pressed={compare} onClick={()=>setCompare(true)}>Before</button><button type="button" aria-pressed={!compare} onClick={()=>setCompare(false)}>After</button></div>}</div>
   {drawing&&image?<FocusOutlineEditor src={image.preview_url} initial={proposal?.focus||c.settings.focus} busy={busy} onPreview={(points,strokes)=>void previewFocus(points,strokes)} onCancel={()=>setDrawing(false)}/>:<><div className={`aiPreviewImage ${busy?'isWorking':''}`} aria-busy={busy}>{image?<div><img src={preview&&!compare?preview:c.src||image.preview_url} alt={preview&&!compare?'AI enhancement result':'Current thermal display'}/>{preview&&!compare&&outline&&proposal&&<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Proposed mask outlines">{proposal.focus&&<polygon className="keepArea" points={proposal.focus.points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>} {proposal.concealed_areas?.map((area,i)=><polygon key={i} className="hideArea" points={area.points.map(p=>`${p.x*1000},${p.y*1000}`).join(' ')}/>)}</svg>}</div>:<div className="aiEmptyImage"><ImagePlus size={40}/><p>Your image will appear here</p><button type="button" disabled={uploading} onClick={()=>fileInput.current?.click()}>Upload image</button></div>}{busy&&<span className="aiProcessingBadge" role="status">Preparing your result…</span>}</div>
   <p className="aiReviewHint">{applied?'Applied to your workspace. Return to save or export your image.':preview?'Check the insulator edges. Use this result, or ask AI for another adjustment.':busy?'AI is selecting the insulator and adjusting the surrounding heat colors.':image?(messages.length?'Reply in the chat to prepare or refine your result.':'Describe your edit and click Enhance with AI. Your result will appear here.'):'Upload a thermal image to begin.'}</p>
   {preview&&<label className="aiOutline"><input type="checkbox" checked={outline} onChange={e=>setOutline(e.target.checked)}/>Show selection outline</label>}</>}
   <div className="aiMeasurementNote"><Check size={17}/><div><b>Original temperature data preserved</b><p>Blue background is a display effect. {c.analysis?.status==='completed'?'Focus readings use the selected insulator area; original full-frame readings remain available.':'Calibrated readings are available only when the image contains supported thermal data.'}</p></div></div>
  </section></div>
  <footer className="aiApplyBar">
   {error&&<p className="aiError" role="alert">{error}</p>}
   {stale&&<p className="aiError">The workspace changed. Send your request again for a fresh result.</p>}
   {applied&&<p role="status" className="aiApplied">Applied. Return to the image, then Save draft or Save to inspection.</p>}
   <div className="aiReviewActions"><div><button type="button" disabled={blocked||!c.undoCount} onClick={()=>{c.undo();setDrawing(false);setApplied(false);setProposal(null);setPreview('');setBase('')}}><Undo2 size={16}/> Undo</button>{proposal&&<button type="button" disabled={busy} onClick={()=>{setProposal(null);setPreview('');setBase('')}}>Discard result</button>}</div>{applied?<button type="button" className="primary" onClick={close}><Check size={16}/> Done — return to image</button>:<button type="button" className="primary" disabled={blocked||drawing||!proposal||stale} onClick={apply}><Check size={16}/> Use this result</button>}</div>
  </footer>
 </dialog>,document.body)}</>;
}
