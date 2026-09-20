import {useEffect, useState} from 'react';
import {ArrowLeft, Images, RefreshCw, Search, ShieldCheck} from 'lucide-react';
import {api, publicApiUrl, type Analysis, type Stats} from './api';
import './admin-work.css';

type Owner = {id:number; username:string; display_name:string; status:string};
type Workspace = Owner & {inspection_count:number; image_count:number};
type Inspection = {id:number; tower_code:string; circuit?:string; phase?:string; created_at?:string; notes?:string; owner:Owner; image_count:number};
type ImageItem = {id:number; name:string; preview_url:string; latest_analysis?:Analysis};
type Review = {id:number; name:string; owner:Owner; created_at?:string; classification:string; analysis?:Analysis; report_analysis?:Analysis; preview_url:string; report_url:string;
  regions:{id:number; name:string; kind:string; statistics?:Stats; minimum_selection?:{temperature_c:number}}[];
  workspace:{notes:{id:string; text:string}[]; drawings:unknown[]; guide_overlays:unknown[]; probes:unknown[]; insulator_label?:string}};
const date = (value?:string) => value ? new Date(value.endsWith('Z')?value:`${value}Z`).toLocaleString() : 'Not recorded';
const temp = (value?:number|null) => value == null ? '—' : `${value.toFixed(1)}°C`;

export default function AdminWorkPage({initialOwnerId}:{initialOwnerId?:number}) {
  const [owners,setOwners]=useState<Workspace[]>([]), [ownerId,setOwnerId]=useState(initialOwnerId ? String(initialOwnerId) : '');
  const [query,setQuery]=useState(''), [search,setSearch]=useState(''), [offset,setOffset]=useState(0), [refresh,setRefresh]=useState(0);
  const [items,setItems]=useState<Inspection[]>([]), [total,setTotal]=useState(0), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [selected,setSelected]=useState<Inspection|null>(null), [images,setImages]=useState<ImageItem[]>([]), [imageId,setImageId]=useState<number>();
  const [review,setReview]=useState<Review|null>(null), [reviewLoading,setReviewLoading]=useState(false), [mode,setMode]=useState<'report'|'original'>('report'), [zoom,setZoom]=useState(100), [imageError,setImageError]=useState(false);
  useEffect(()=>{let live=true;api<Workspace[]>('/api/admin/workspaces').then(data=>{if(live)setOwners(data)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[refresh]);
  useEffect(()=>{let live=true;setLoading(true);setError('');setItems([]);
    const params=new URLSearchParams({offset:String(offset),limit:'30',q:search});if(ownerId)params.set('owner_id',ownerId);
    api<{items:Inspection[];total:number}>(`/api/admin/inspections?${params}`).then(data=>{if(live){setItems(data.items);setTotal(data.total)}}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});
    return()=>{live=false}
  },[ownerId,search,offset,refresh]);
  useEffect(()=>{if(!selected)return;let live=true;setLoading(true);setImages([]);setImageId(undefined);setReview(null);setError('');
    api<ImageItem[]>(`/api/admin/inspections/${selected.id}/images`).then(data=>{if(live){setImages(data);setImageId(data[0]?.id)}}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});
    return()=>{live=false}
  },[selected?.id,refresh]);
  useEffect(()=>{setReview(null);setImageError(false);setZoom(100);if(!imageId)return;let live=true;setReviewLoading(true);setError('');
    api<Review>(`/api/admin/images/${imageId}/review`).then(data=>{if(live)setReview(data)}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setReviewLoading(false)});
    return()=>{live=false}
  },[imageId,refresh]);
  const workspace=owners.find(owner=>String(owner.id)===ownerId);
  const stats=review?.report_analysis?.statistics;
  return <section className="adminWorkPage">
    <header className="adminWorkHeading"><div><div className="authEyebrow"><ShieldCheck size={16}/> ADMIN REVIEW</div><h1>All user work</h1><p>Review saved inspections and thermal images across all accounts.</p></div><button className="ghost" onClick={()=>setRefresh(value=>value+1)}><RefreshCw size={16}/> Refresh</button></header>
    <div className="adminReviewNotice">Read-only review · Changes still unsaved in a user's browser are not shown here.</div>
    {error&&<p className="authError" role="alert">{error}</p>}
    {!selected?<>
      <div className="adminWorkTotals"><span><b>{workspace?workspace.inspection_count:owners.reduce((sum,item)=>sum+item.inspection_count,0)}</b> inspections</span><span><b>{workspace?workspace.image_count:owners.reduce((sum,item)=>sum+item.image_count,0)}</b> images</span><span><b>{owners.length}</b> user workspaces</span></div>
      <form className="adminWorkFilters" onSubmit={event=>{event.preventDefault();setSearch(query);setOffset(0)}}><label>User<select value={ownerId} onChange={event=>{setOwnerId(event.target.value);setOffset(0)}}><option value="">All users</option>{owners.map(owner=><option key={owner.id} value={owner.id}>{owner.display_name} (@{owner.username}){owner.status==='Active'?'':` · ${owner.status}`} — {owner.image_count} images</option>)}</select></label><label>Search<input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Tower, circuit, user, or image name"/></label><button className="primary"><Search size={16}/> Search</button></form>
      {loading?<p role="status">Loading inspections…</p>:!items.length?<div className="adminWorkEmpty"><Images/><h2>No inspections found</h2><p>{ownerId?'This user has no inspections matching your search.':'Try another search or select a different user.'}</p></div>:<div className="adminInspectionGrid">{items.map(item=><button className="adminInspectionCard" key={item.id} onClick={()=>setSelected(item)}><span className="adminOwner">{item.owner.display_name} <small>@{item.owner.username} · {item.owner.status}</small></span><h2>{item.tower_code}</h2><p>{[item.circuit,item.phase].filter(Boolean).join(' · ')||'Thermal inspection'}</p><span><Images size={16}/> {item.image_count} {item.image_count===1?'image':'images'}</span><small>{date(item.created_at)}</small><strong>View inspection →</strong></button>)}</div>}
      <div className="adminWorkPagination"><span>{total} matching inspections</span><button className="ghost" disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-30))}>Previous</button><button className="ghost" disabled={offset+30>=total||loading} onClick={()=>setOffset(offset+30)}>Next</button></div>
    </>:<>
      <button className="ghost" onClick={()=>{setSelected(null);setImageId(undefined);setReview(null);setError('')}}><ArrowLeft size={16}/> All inspections</button>
      <div className="adminInspectionTitle"><h2>{selected.tower_code}</h2><p>{selected.owner.display_name} · @{selected.owner.username} · {selected.owner.status}</p>{selected.notes&&<p>{selected.notes}</p>}</div>
      {loading?<p role="status">Loading images…</p>:!images.length?<p>This inspection has no uploaded images.</p>:<div className="adminReviewLayout"><div className="adminImageList" aria-label="Inspection images">{images.map(item=><button key={item.id} className={item.id===imageId?'active':''} onClick={()=>{setImageId(item.id);setMode('report')}}><img src={item.preview_url} alt="" loading="lazy"/><strong>{item.name}</strong><small>{item.latest_analysis?.status||'Not processed'}</small></button>)}</div><div className="adminReviewContent">
        {reviewLoading?<p role="status">Loading saved work…</p>:review&&<>
          <h3>{review.name}</h3><p className="adminReviewMeta">Uploaded {date(review.created_at)} · Processing: {review.analysis?.status||'Not processed'}</p>
          <div className="adminReviewControls"><button className={mode==='report'?'primary':'ghost'} onClick={()=>{setMode('report');setImageError(false)}}>Saved work</button><button className={mode==='original'?'primary':'ghost'} onClick={()=>{setMode('original');setImageError(false)}}>Original preview</button><label>Zoom <input aria-label="Review image zoom" type="range" min="50" max="300" step="25" value={zoom} onChange={event=>setZoom(Number(event.target.value))}/>{zoom}%</label><button className="ghost" onClick={()=>setZoom(100)}>Fit</button></div>
          {imageError?<p className="authError" role="alert">This preview could not be loaded. Try Original preview or Refresh.</p>:<div className="adminReviewViewport"><img key={`${review.id}-${mode}-${refresh}`} src={`${publicApiUrl(mode==='report'?review.report_url:review.preview_url)}?revision=${refresh}`} alt={`${mode==='report'?'Saved annotations and enhancements':'Original thermal preview'}: ${review.name}`} style={{width:`${zoom}%`}} onError={()=>setImageError(true)}/></div>}
          <div className="adminReviewStats"><span>MAX <b>{temp(stats?.maximum_c)}</b></span><span>MIN <b>{temp(stats?.minimum_c)}</b></span><span>AVG <b>{temp(stats?.mean_c)}</b></span><span>Regions <b>{review.regions.length}</b></span></div>
          <p className="adminReviewMeta">Full image statistics{review.report_analysis?` · Analysis v${review.report_analysis.version}`:''}. Saved work includes stored enhancements, labels, drawings, notes, probes, and supporting images.</p>
          {review.regions.length>0&&<div className="usersTableWrap"><table className="usersTable"><thead><tr><th>Measurement</th><th>Type</th><th>MAX</th><th>MIN</th><th>AVG</th></tr></thead><tbody>{review.regions.map(region=><tr key={region.id}><td>{region.name}</td><td>{region.kind}</td><td>{temp(region.statistics?.maximum_c)}</td><td>{temp(region.minimum_selection?.temperature_c??region.statistics?.minimum_c)}</td><td>{temp(region.statistics?.mean_c)}</td></tr>)}</tbody></table></div>}
          {review.workspace.notes.length>0&&<div className="adminReviewNotes"><h3>Saved notes</h3>{review.workspace.notes.map(note=><p key={note.id}>{note.text}</p>)}</div>}
        </>}
      </div></div>}
    </>}
  </section>
}
