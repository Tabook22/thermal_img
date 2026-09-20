import {useEffect,useState} from 'react';
import {Download,RefreshCw} from 'lucide-react';
import {api,publicApiUrl} from './api';
import {useAuth} from './Auth';
import './activity.css';

type EventRow={id:number;username:string;display_name:string;at:string;category:string;action:string;summary:string;outcome:string;source:string;image_name?:string};
type Visit={id:string;username:string;started_at:string;last_seen_at:string;ended_at?:string;status:string;page:string;foreground_seconds:number};
type Log={total:number;events:EventRow[];visits:Visit[];summary:{sign_ins:number;images:number;actions:number;foreground_seconds:number;focus:{category:string;count:number}[];top_images:{id:number;name:string;actions:number}[]}};
type Owner={id:number;username:string;display_name:string;status:string};
const localDay=(daysAgo=0)=>{const d=new Date();d.setDate(d.getDate()-daysAgo);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const at=(date?:string)=>date?new Date(date).toLocaleString():'—';
const duration=(seconds:number)=>`${Math.floor(seconds/3600)}h ${Math.floor(seconds%3600/60)}m`;
const categories=['access','navigation','image','inspection','measurement','enhancement','annotation','editing','export','review','library','research','account','settings'];

export default function ActivityPage({initialUserId}:{initialUserId?:number}){
  const {user}=useAuth(),admin=user.role==='admin';
  const [owners,setOwners]=useState<Owner[]>([]),[owner,setOwner]=useState(initialUserId?String(initialUserId):admin?'':String(user.id));
  const [from,setFrom]=useState(localDay(6)),[to,setTo]=useState(localDay()),[category,setCategory]=useState(''),[offset,setOffset]=useState(0),[revision,setRevision]=useState(0);
  const [data,setData]=useState<Log|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const valid=!!from&&!!to&&from<=to;
  const params=new URLSearchParams({category});if(owner)params.set('user_id',owner);
  if(valid){const until=new Date(`${to}T00:00:00`);until.setDate(until.getDate()+1);params.set('since',new Date(`${from}T00:00:00`).toISOString());params.set('until',until.toISOString())}
  const query=params.toString();
  useEffect(()=>{if(admin)void api<Owner[]>('/api/admin/workspaces').then(setOwners).catch(e=>setError(e.message))},[admin,revision]);
  useEffect(()=>{if(!valid){setData(null);setLoading(false);return}let live=true;setLoading(true);setError('');
    api<Log>(`/api/activity/log?${query}&offset=${offset}&limit=50`).then(result=>{if(live)setData(result)}).catch(e=>{if(live){setError(e.message);setData(null)}}).finally(()=>{if(live)setLoading(false)});
    return()=>{live=false}
  },[query,offset,revision,valid]);
  const reset=()=>setOffset(0);
  return <section className="activityPage"><div className="activityHeading"><div><div className="authEyebrow">{admin?'ADMINISTRATION':'MY WORKSPACE'}</div><h1>Activity log</h1><p>Dated summaries of sign-ins, images, actions, and time in the application.</p></div><button className="ghost" onClick={()=>setRevision(v=>v+1)}><RefreshCw size={16}/> Refresh</button></div>
    <p className="activityDisclosure">Work actions are recorded for administrator review. Times below use {Intl.DateTimeFormat().resolvedOptions().timeZone}. Browser events are reported by the app; server events confirm requests. No passwords or note contents are logged.</p>
    <div className="activityFilters">{admin&&<label>User<select value={owner} onChange={e=>{setOwner(e.target.value);reset()}}><option value="">All users</option>{owners.map(item=><option key={item.id} value={item.id}>{item.display_name} (@{item.username}){item.status==='Active'?'':` · ${item.status}`}</option>)}</select></label>}<label>From<input type="date" value={from} onChange={e=>{setFrom(e.target.value);reset()}}/></label><label>Through<input type="date" value={to} onChange={e=>{setTo(e.target.value);reset()}}/></label><label>Action type<select value={category} onChange={e=>{setCategory(e.target.value);reset()}}><option value="">All actions</option>{categories.map(item=><option key={item}>{item}</option>)}</select></label></div>
    {!valid&&<p className="authError">Choose a valid start and end date.</p>}{error&&<p className="authError" role="alert">{error}</p>}
    {loading?<p role="status">Loading activity…</p>:data&&<>
      <div className="activitySummary"><span><b>{data.summary.sign_ins}</b> successful sign-ins</span><span><b>{data.summary.images}</b> images involved</span><span><b>{data.summary.actions}</b> recorded events</span><span><b>{duration(data.summary.foreground_seconds)}</b> estimated foreground time</span></div>
      <p className="activityHint">Summary covers the selected user and dates. Foreground time counts visible tabs for visits started in that period; it is not a measure of productivity. Simultaneous tabs may overlap. Tracking begins with this update.</p>
      <div className="activityFocus"><div><h3>Activity focus</h3>{data.summary.focus.length?data.summary.focus.map(item=><span key={item.category}>{item.category} <b>{item.count}</b></span>):<p>No recorded activity in this period.</p>}</div><div><h3>Most active images</h3>{data.summary.top_images.map(item=><p key={item.id}>{item.name} <b>{item.actions} events</b></p>)}</div></div>
      <details className="activityVisits"><summary>Application visits · latest {data.visits.length}</summary><p className="activityHint">Sign-out is confirmed. Closing or reloading is browser-reported. After five minutes without contact, the last contact is shown as the estimated end; a crash, lost connection, or suspended tab cannot provide an exact closing time.</p><div className="usersTableWrap"><table className="usersTable"><thead><tr><th>User</th><th>Entered</th><th>Ended / last contact</th><th>Last page</th><th>Status</th><th>Foreground</th></tr></thead><tbody>{data.visits.map(visit=><tr key={visit.id}><td>@{visit.username}</td><td>{at(visit.started_at)}</td><td>{at(visit.ended_at||visit.last_seen_at)}</td><td>{visit.page}</td><td>{visit.status}</td><td>{duration(visit.foreground_seconds)}</td></tr>)}</tbody></table></div></details>
      <div className="activityTimelineHeading"><h2>Action history</h2><a className="ghost" href={publicApiUrl(`/api/activity/export?${query}&format=csv`)}><Download size={15}/> CSV log</a><a className="ghost" href={publicApiUrl(`/api/activity/export?${query}&format=txt`)}><Download size={15}/> Text log</a></div><p className="activityHint">Exports use UTC timestamps and include all matching actions, not just this page.</p>
      <div className="usersTableWrap"><table className="usersTable activityTable"><thead><tr><th>Date & time</th><th>User</th><th>Action</th><th>Image</th><th>Result / source</th></tr></thead><tbody>{data.events.map(event=><tr key={event.id}><td>{at(event.at)}</td><td>{event.display_name}<small>@{event.username}</small></td><td>{event.summary}<small>{event.category}</small></td><td>{event.image_name||'—'}</td><td><span className={event.outcome==='failed'?'activityFailed':''}>{event.outcome}</span><small>{event.source}</small></td></tr>)}</tbody></table>{!data.events.length&&<p className="activityEmpty">No events match these filters.</p>}</div>
      <div className="activityPagination"><span>{data.total} matching events</span><button className="ghost" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous</button><button className="ghost" disabled={offset+50>=data.total} onClick={()=>setOffset(offset+50)}>Next</button></div>
    </>}
  </section>
}
