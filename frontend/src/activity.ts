import {useEffect,useRef,useState} from 'react';
import {api,apiFetch} from './api';

export const LOCAL_ACTIVITY=new Set(['Add temperature marker','Move temperature marker','Delete temperature marker','Move insulator label','Resize insulator label','Add inner insulator label','Add outer insulator label','Remove inner insulator label','Remove outer insulator label','Move supporting image','Resize supporting image','Zoom supporting image','Remove supporting image']);
export function recordActivity(action:'tool_selected'|'local_edit'|'undo'|'redo'|'image_close'|'display_change',imageId?:number,detail=''){
  void api('/api/activity/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,image_id:imageId??null,detail})}).catch(()=>{window.dispatchEvent(new Event('thermal-activity-error'))});
}

export function useActivityTracking(page:string,imageId:number|undefined,tool:string){
  const current=useRef({page,imageId});current.current={page,imageId};
  const sendRef=useRef<()=>void>(()=>{}),[interrupted,setInterrupted]=useState(false);
  useEffect(()=>{
    let visitId=crypto.randomUUID(),sequence=0,live=true,sending=false,pending=false,pendingClose=false;
    const send=(ending=false)=>{
      if(sending){pending=true;pendingClose=pendingClose||ending;return}
      sending=true;
      const state=current.current;
      const payload={visit_id:visitId,sequence:++sequence,page:state.page,image_id:state.page==='workspace'?state.imageId??null:null,visible:document.visibilityState==='visible',ending};
      void apiFetch('/api/activity/presence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),keepalive:ending}).then(async response=>{
        if(!response.ok)throw new Error('Tracking unavailable');
        const result=await response.json();if(!live)return;
        if(result.restart&&!ending){visitId=crypto.randomUUID();sequence=0;send()}
        setInterrupted(false);
      }).catch(()=>{if(live)setInterrupted(true)}).finally(()=>{sending=false;if(pending&&live){const close=pendingClose;pending=false;pendingClose=false;send(close)}});
    };
    sendRef.current=()=>send();send();
    const timer=window.setInterval(()=>send(),30000);
    const visibility=()=>send(),close=()=>send(true),resume=(event:PageTransitionEvent)=>{if(event.persisted){visitId=crypto.randomUUID();sequence=0;send()}};
    const error=()=>setInterrupted(true);
    document.addEventListener('visibilitychange',visibility);window.addEventListener('pagehide',close);window.addEventListener('pageshow',resume);window.addEventListener('online',visibility);window.addEventListener('thermal-activity-error',error);
    return()=>{live=false;clearInterval(timer);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('pagehide',close);window.removeEventListener('pageshow',resume);window.removeEventListener('online',visibility);window.removeEventListener('thermal-activity-error',error);sendRef.current=()=>{}};
  },[]);
  const previousContext=useRef({page,imageId});
  useEffect(()=>{if(previousContext.current.page===page&&previousContext.current.imageId===imageId)return;previousContext.current={page,imageId};sendRef.current()},[page,imageId]);
  const previousTool=useRef(tool);
  useEffect(()=>{if(previousTool.current!==tool&&page==='workspace')recordActivity('tool_selected',imageId,tool);previousTool.current=tool},[tool,page,imageId]);
  return interrupted;
}
