import {api} from './api';

type Inspection={id:number;tower_code:string;circuit?:string;phase?:string;created_at:string};
type Image={id:number;name:string;classification:string;sha256:string;preview_url:string};
let opening:{key:string;resumeKey?:string;request:Promise<{image:Image}>}|undefined;

export function openInspectionImage(userId:number){
  const ticket=new URLSearchParams(location.hash.slice(1)).get('inspection');
  const existing=new URLSearchParams(location.search).get('inspection_image');
  if(!ticket&&!existing)return null;
  const key=`${userId}:${ticket?`ticket:${ticket}`:`image:${existing}`}`;
  // React StrictMode remounts must share the single-use ticket request.
  if(opening&&(opening.key===key||opening.resumeKey===key))return opening.request;
  const request=ticket
    ?api<{image:Image}>('/api/inspection-bridge/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket})})
    :api<{image:Image}>(`/api/inspection-bridge/images/${encodeURIComponent(existing!)}`);
  const entry={key,request} as NonNullable<typeof opening>;
  entry.request=request.then(result=>{
    if(opening===entry){
      entry.resumeKey=`${userId}:image:${result.image.id}`;
      history.replaceState(null,'',`${import.meta.env.BASE_URL}?inspection_image=${result.image.id}`);
    }
    return result;
  });
  opening=entry;
  return entry.request;
}

export async function loadInitialWorkspace(userId:number,onInspections:(items:Inspection[])=>void){
  // Choose the source before any asynchronous work. A transfer must never fall
  // back to an unrelated recent image, even if the link fails or expires.
  const transferred=openInspectionImage(userId);
  const inspections=api<Inspection[]>('/api/inspections').then(items=>{onInspections(items);return items});
  if(transferred){
    void inspections.catch(()=>{});
    return (await transferred).image;
  }
  const recent=(await inspections)[0];
  if(!recent)return undefined;
  return (await api<Image[]>(`/api/inspections/${recent.id}/images`))[0];
}
