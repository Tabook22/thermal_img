import {useEffect,useState,type FormEvent} from 'react';
import {CheckCircle2,Eye,EyeOff,KeyRound,PlugZap,ShieldCheck} from 'lucide-react';
import {api} from './api';
import './ai-settings.css';

type Status={configured:boolean;provider:string;model:string;saved_in_env:boolean};
export default function AISettings(){
 const [status,setStatus]=useState<Status|null>(null),[key,setKey]=useState(''),[show,setShow]=useState(false);
 const [busy,setBusy]=useState<'load'|'save'|'test'|null>('load'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[connected,setConnected]=useState(false);
 const load=async()=>{setBusy('load');setError('');try{setStatus(await api<Status>('/api/admin/settings/ai'))}catch(e:any){setError(e.message)}finally{setBusy(null)}};
 useEffect(()=>{void load()},[]);
 const save=async(e:FormEvent)=>{e.preventDefault();setBusy('save');setError('');setNotice('');setConnected(false);
  try{setStatus(await api<Status>('/api/admin/settings/ai',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key.trim()})}));setKey('');setShow(false);setNotice('API key saved in the server .env file and activated. Test the connection to verify access.')}catch(e:any){setError(e.message)}finally{setBusy(null)}
 };
 const test=async()=>{setBusy('test');setError('');setNotice('');setConnected(false);try{const result=await api<{message:string}>('/api/admin/settings/ai/test',{method:'POST'});setConnected(true);setNotice(result.message)}catch(e:any){setError(e.message)}finally{setBusy(null)}};
 return <section className="aiSettings" aria-labelledby="ai-settings-title">
  <div className="aiSettingsHeader"><div className="aiSettingsTitle"><span><KeyRound size={22}/></span><div><small>ADMINISTRATOR ONLY</small><h2 id="ai-settings-title">AI connection</h2></div></div><span className={`aiKeyStatus ${connected?'connected':''}`}>{busy==='load'?'Checking…':connected?'Connection verified':status?.configured?'API key configured':'Not connected'}</span></div>
  <p>Connect OpenAI so your team can describe an edit and receive an AI selection and background enhancement preview.</p>
  <form onSubmit={save} autoComplete="off">
   <label htmlFor="openai-api-key">{status?.configured?'Replace OpenAI API key':'OpenAI API key'}</label>
   <div className="aiKeyInput"><input id="openai-api-key" type={show?'text':'password'} value={key} onChange={e=>{setKey(e.target.value);setNotice('')}} placeholder={status?.configured?'Saved key is hidden. Enter a new key to replace it.':'Paste your OpenAI API key (sk-…)'} autoComplete="new-password" spellCheck={false} autoCapitalize="none" maxLength={1003} disabled={!!busy} required/><button type="button" disabled={!key||!!busy} aria-label={show?'Hide entered API key':'Show entered API key'} onClick={()=>setShow(!show)}>{show?<EyeOff size={18}/>:<Eye size={18}/>}</button></div>
   <p className="aiKeyHint"><ShieldCheck size={15}/>Stored in a private server .env file. The saved key is never displayed or returned to the browser. Changes apply immediately.</p>
   <div className="aiSettingsActions"><button type="submit" className="primary" disabled={!!busy||!key.trim()}><ShieldCheck size={16}/>{busy==='save'?'Saving…':'Save API key'}</button><button type="button" className="ghost" disabled={!!busy||!status?.configured||!!key.trim()} onClick={()=>void test()}><PlugZap size={16}/>{busy==='test'?'Testing connection…':'Test connection'}</button>{!status&&!busy&&<button type="button" className="ghost" onClick={()=>void load()}>Retry loading settings</button>}</div>
  </form>
  {error&&<p className="aiSettingsMessage errorMessage" role="alert">{error}</p>}{notice&&<p className="aiSettingsMessage successMessage" role="status">{connected&&<CheckCircle2 size={17}/>} {notice}</p>}
  <div className="aiSettingsDetails"><span>Provider: OpenAI{status&&` · Image assistant: ${status.model}`}</span><span>Testing sends a short text request; no inspection image is sent. API usage is billed to the connected OpenAI project.</span></div>
 </section>;
}
