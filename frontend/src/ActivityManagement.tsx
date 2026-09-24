import {useEffect,useRef,useState} from 'react';
import {api} from './api';

type RecordingUser={id:number;username:string;display_name:string;deleted:boolean;enabled:boolean;events:number;visits:number};
type Preview={user_id:number|null;since:string;until:string;events:number;visits:number};

export default function ActivityManagement({owner,since,until,revision,onChanged,onSelect}:{owner:string;since?:string;until?:string;revision:number;onChanged:()=>void;onSelect:(id:string)=>void}){
  const [users,setUsers]=useState<RecordingUser[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [allHistory,setAllHistory]=useState(false),[preview,setPreview]=useState<Preview|null>(null);
  useEffect(()=>{let live=true;api<RecordingUser[]>('/api/activity/management').then(rows=>{if(live)setUsers(rows)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[revision]);
  const scopeVersion=useRef(0);
  useEffect(()=>{scopeVersion.current++;setPreview(null)},[owner,since,until,allHistory]);
  const target=owner?users.find(row=>String(row.id)===owner):null;
  const targetName=owner?(target?`@${target.username}`:'selected user'):'ALL users';
  async function toggle(row:RecordingUser){
    setBusy(true);setError('');setMessage('');
    try{await api(`/api/activity/management/${row.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!row.enabled})});setMessage(`Recording ${row.enabled?'disabled':'enabled'} for @${row.username}.`);onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function inspect(){
    const version=scopeVersion.current;
    setBusy(true);setError('');setMessage('');
    try{const result=await api<Preview>('/api/activity/cleanup/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:owner?Number(owner):null,since:allHistory?'1970-01-01T00:00:00Z':since,until:allHistory?new Date().toISOString():until})});if(version===scopeVersion.current)setPreview(result)}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function remove(){
    if(!preview)return;
    setBusy(true);setError('');
    try{const result=await api<{events:number;visits:number}>('/api/activity/cleanup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...preview,confirm:true})});setPreview(null);setMessage(`Deleted ${result.events} events and ${result.visits} visits. Images and inspections were preserved.`);onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <details className="activityManagement"><summary>Manage recording &amp; storage · administrator only</summary>
    <p className="activityHint">Turn recording on or off for each account. Turning it off stops new events and visits; existing history remains available. Turning it on resumes recording without filling the gap.</p>
    {error&&<p className="authError" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <div className="usersTableWrap"><table className="usersTable"><thead><tr><th>User</th><th>Recording</th><th>Stored events</th><th>Stored visits</th><th>Actions</th></tr></thead><tbody>{users.map(row=><tr key={row.id}><td>{row.display_name}<small> @{row.username}{row.deleted?' · Deleted account':''}</small></td><td>{row.enabled?'On':'Off'}</td><td>{row.events.toLocaleString()}</td><td>{row.visits.toLocaleString()}</td><td><button className="ghost" disabled={busy} aria-label={`${row.enabled?'Disable':'Enable'} recording for ${row.username}`} onClick={()=>void toggle(row)}>{row.enabled?'Turn off':'Turn on'}</button> <button className="ghost" onClick={()=>onSelect(String(row.id))}>View logs</button></td></tr>)}</tbody></table></div>
    <div className="activityCleanup"><h3>Delete stored logs</h3><p>Scope: <b>{targetName}</b></p><label>Period <select disabled={busy} value={allHistory?'all':'dates'} onChange={e=>setAllHistory(e.target.value==='all')}><option value="dates">Selected dates above</option><option value="all">All history up to now</option></select></label>
      <p className="activityHint">Deletes all action types and visits that started in this period. The action-type filter does not limit deletion. Images, reports, inspections, and accounts stay intact. Download any logs you need first.</p>
      <button className="ghost" disabled={busy||(!allHistory&&(!since||!until))} onClick={()=>void inspect()}>Preview deletion</button>
      {preview&&<div className="activityDeleteConfirm" role="region" aria-label="Confirm log deletion"><h3>Confirm deletion for {targetName}</h3><p><b>{preview.events.toLocaleString()} events</b> and <b>{preview.visits.toLocaleString()} visits</b><br/>{new Date(preview.since).toLocaleString()} to {new Date(preview.until).toLocaleString()} (end exclusive)</p><p>This cannot be undone in the application. New activity may be recorded again while recording is on.</p><button className="ghost" disabled={busy} onClick={()=>setPreview(null)}>Cancel</button> <button className="danger" disabled={busy||preview.events+preview.visits===0} onClick={()=>void remove()}>{busy?'Working…':'Delete these logs permanently'}</button></div>}
      <p className="activityHint">Deleted database space is reused for new records; the SQLite file may not shrink immediately. Existing backups and previously downloaded logs are unaffected.</p>
    </div>
  </details>
}
