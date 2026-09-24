import {useEffect,useState} from 'react';
import {api} from './api';
import './inspection-bridge.css';

type Link={title:string;return_path:string;external_image_id:number;expires_at:string};

export default function InspectionBridge({imageId,payload,ready,onSaved}:{imageId?:number;payload:unknown;ready:boolean;onSaved:()=>void}){
  const [link,setLink]=useState<Link|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
  useEffect(()=>{let live=true;setLink(null);setMessage('');setError('');if(imageId)void api<{link:Link|null}>(`/api/inspection-bridge/images/${imageId}`).then(result=>{if(live)setLink(result.link)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[imageId]);
  if(!link)return null;
  async function save(){
    setBusy(true);setMessage('');setError('');
    try{await api(`/api/inspection-bridge/images/${imageId}/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});onSaved();setMessage('Saved to the inspection. The original image is preserved.');
      if('BroadcastChannel' in window){const channel=new BroadcastChannel('thermal-inspection-saved');channel.postMessage({image_id:link!.external_image_id});channel.close()}
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <section className="inspectionBridge"><div><b>Inspection image · {link.title}</b><small>Enhance, measure, and annotate here, then save the processed copy to its inspection.</small>{message&&<p role="status">{message}</p>}{error&&<p className="authError" role="alert">{error}</p>}</div><button className="primary" disabled={busy||!ready} onClick={()=>void save()}>{busy?'Saving to inspection…':'Save back to inspection'}</button><a className="ghost" href={link.return_path} target="_blank" rel="noopener noreferrer">View inspection ↗</a></section>;
}
