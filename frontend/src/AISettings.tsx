import {useEffect,useState,type FormEvent} from 'react';
import {CheckCircle2,Eye,EyeOff,KeyRound,PlugZap,ShieldCheck} from 'lucide-react';
import {api} from './api';
import './ai-settings.css';

type Provider={id:string;name:string;configured:boolean;model:string;default_model:string};
type Status={configured:boolean;provider:string;provider_name:string;model:string;saved_in_env:boolean;providers:Provider[]};
export default function AISettings(){
 const [status,setStatus]=useState<Status|null>(null),[key,setKey]=useState(''),[show,setShow]=useState(false);
 const [provider,setProvider]=useState('openai'),[model,setModel]=useState('');
 const [busy,setBusy]=useState<'load'|'save'|'test'|null>('load'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[connected,setConnected]=useState(false);
 const sync=(value:Status)=>{setStatus(value);setProvider(value.provider);setModel(value.model)};
 const load=async()=>{setBusy('load');setError('');try{sync(await api<Status>('/api/admin/settings/ai'))}catch(e:any){setError(e.message)}finally{setBusy(null)}};
 useEffect(()=>{void load()},[]);
 const selected=status?.providers.find(p=>p.id===provider);
 const dirty=!!key.trim()||provider!==status?.provider||model.trim()!==status?.model;
 const chooseProvider=(id:string)=>{setProvider(id);setModel(status?.providers.find(p=>p.id===id)?.model||'');setKey('');setShow(false);setError('');setNotice('');setConnected(false)};
 const save=async(e:FormEvent)=>{
  e.preventDefault();setBusy('save');setError('');setNotice('');setConnected(false);
  try{
   const next=await api<Status>('/api/admin/settings/ai',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider,model:model.trim(),...(key.trim()?{api_key:key.trim()}:{})})});
   sync(next);setKey('');setShow(false);setNotice(`${next.provider_name} settings saved in the server .env file and activated. Test the connection to verify access.`);
  }catch(e:any){setError(e.message)}finally{setBusy(null)}
 };
 const test=async()=>{setBusy('test');setError('');setNotice('');setConnected(false);try{const result=await api<{message:string}>('/api/admin/settings/ai/test',{method:'POST'});setConnected(true);setNotice(result.message)}catch(e:any){setError(e.message)}finally{setBusy(null)}};
 return <section className="aiSettings" aria-labelledby="ai-settings-title">
  <div className="aiSettingsHeader"><div className="aiSettingsTitle"><span><KeyRound size={22}/></span><div><small>ADMINISTRATOR ONLY</small><h2 id="ai-settings-title">AI connection</h2></div></div><span className={`aiKeyStatus ${connected?'connected':''}`}>{busy==='load'?'Checking…':connected?'Connection verified':status?.configured?'API key configured':'Not connected'}</span></div>
  <p>Choose who provides your AI, select a model, and enter that provider’s API key. Your team will use this connection for image enhancement.</p>
  {status?.configured&&<p className="aiActiveProvider">Active: <b>{status.provider_name}</b> · {status.model}</p>}
  <form onSubmit={save} autoComplete="off">
   <div className="aiProviderFields"><div><label htmlFor="ai-provider">Provider · who issued your key?</label><select id="ai-provider" value={provider} onChange={e=>chooseProvider(e.target.value)} disabled={!!busy||!status}>{status?.providers.map(p=><option value={p.id} key={p.id}>{p.name}{p.configured?' · key saved':''}</option>)}</select></div><div><label htmlFor="ai-model">Model ID</label><input id="ai-model" value={model} list="ai-model-options" onChange={e=>{setModel(e.target.value);setConnected(false);setNotice('')}} disabled={!!busy||!status} required maxLength={120} autoComplete="off" spellCheck={false}/><datalist id="ai-model-options">{selected&&<option value={selected.default_model}/>}</datalist></div></div>
   <p className="aiKeyHint">Use a model with image understanding and structured output. The suggested model can be replaced with one available to your account.</p>
   <label htmlFor="openai-api-key">{selected?.name||'Provider'} API key {selected?.configured?'· saved (replace only if needed)':''}</label>
   <div className="aiKeyInput"><input id="openai-api-key" type={show?'text':'password'} value={key} onChange={e=>{setKey(e.target.value);setNotice('');setConnected(false)}} placeholder={selected?.configured?'Leave blank to keep this provider’s saved key.':`Paste the API key from ${selected?.name||'your selected provider'}`} autoComplete="new-password" spellCheck={false} autoCapitalize="none" maxLength={1010} disabled={!!busy||!status} required={!selected?.configured}/><button type="button" disabled={!key||!!busy} aria-label={show?'Hide entered API key':'Show entered API key'} onClick={()=>setShow(!show)}>{show?<EyeOff size={18}/>:<Eye size={18}/>}</button></div>
   <p className="aiKeyHint"><ShieldCheck size={15}/>Each provider’s key is saved separately in a private server .env file. Saved keys are never returned to the browser. Changes apply when you save.</p>
   {dirty&&status&&<p className="aiUnsaved" role="status">Save your selection before testing. Switching providers requires that provider’s own key.</p>}
   <div className="aiSettingsActions"><button type="submit" className="primary" disabled={!!busy||!status||!model.trim()||(!key.trim()&&!selected?.configured)||!dirty}><ShieldCheck size={16}/>{busy==='save'?'Saving…':'Save AI settings'}</button><button type="button" className="ghost" disabled={!!busy||!status?.configured||dirty} onClick={()=>void test()}><PlugZap size={16}/>{busy==='test'?'Testing connection…':'Test connection'}</button>{!status&&!busy&&<button type="button" className="ghost" onClick={()=>void load()}>Retry loading settings</button>}</div>
  </form>
  {error&&<p className="aiSettingsMessage errorMessage" role="alert">{error}</p>}{notice&&<p className="aiSettingsMessage successMessage" role="status">{connected&&<CheckCircle2 size={17}/>} {notice}</p>}
  <div className="aiSettingsDetails"><span>Testing sends a short text request to the saved provider; no inspection image is sent. API usage is billed by that provider.</span><span>This selection controls image enhancement. Online reference search uses your separately saved OpenAI key.</span></div>
 </section>;
}
