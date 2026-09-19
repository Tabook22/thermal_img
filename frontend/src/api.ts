export const publicApiUrl=(path:string)=>path.startsWith('/api/')?`${import.meta.env.BASE_URL.replace(/\/$/,'')}${path}`:path;
const publicUrls=(value:any):any=>{
 if(Array.isArray(value))return value.map(publicUrls);
 if(value&&typeof value==='object')for(const name of Object.keys(value)){
  if(name==='preview_url'&&typeof value[name]==='string')value[name]=publicApiUrl(value[name]);
  else if(value[name]&&typeof value[name]==='object')value[name]=publicUrls(value[name]);
 }
 return value;
};
export const api=async<T>(path:string,init?:RequestInit):Promise<T>=>{const r=await fetch(publicApiUrl(path),init);const data=await r.json().catch(()=>({}));if(!r.ok){const detail=data.detail??data.error;const message=typeof detail==='string'?detail:detail?.message||(Array.isArray(detail)?detail.map((x:any)=>`${(x.loc||[]).slice(1).join('.')}: ${x.msg}`).join('; '):JSON.stringify(detail));throw new Error(message||`Request failed (${r.status})`)}return publicUrls(data)};
export type Stats={minimum_c:number|null;maximum_c:number|null;mean_c:number|null;valid_pixels:number;minimum_location:{x:number;y:number}|null;maximum_location:{x:number;y:number}|null};
export type Analysis={id:number;status:string;version:number;sdk_version?:string;width?:number;height?:number;statistics?:Stats;error?:string;parameters?:Record<string,number>};
