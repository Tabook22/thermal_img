import {useEffect,useMemo,useRef,useState,type PointerEvent as ReactPointerEvent} from 'react';
import {createPortal} from 'react-dom';
import {ExternalLink,File,FilePlus2,FileText,Film,Grip,Image as ImageIcon,Music2,Save,Search,Trash2,X} from 'lucide-react';
import {api,publicApiUrl} from './api';
import './library-manager.css';

type LibraryDocument={id:string;filename:string;pages:number;passages:number;uploaded_at:string};
type Props={open:boolean;onClose:()=>void;onChange?:()=>void};
const extension=(name:string)=>name.split('.').pop()?.toLowerCase()||'';
const textExtensions=new Set(['txt','md','csv']);
const imageExtensions=new Set(['jpg','jpeg','png']);
const audioExtensions=new Set(['mp3','wav','m4a','ogg']);
const videoExtensions=new Set(['mp4','webm','mov']);
const kind=(name:string)=>{const ext=extension(name);return ext==='pdf'?'PDF':textExtensions.has(ext)?'Text':imageExtensions.has(ext)?'Image':audioExtensions.has(ext)?'Audio':videoExtensions.has(ext)?'Video':'File'};
const icon=(name:string)=>{const type=kind(name);return type==='Text'?<FileText size={18}/>:type==='Image'?<ImageIcon size={18}/>:type==='Audio'?<Music2 size={18}/>:type==='Video'?<Film size={18}/>:<File size={18}/>};

export default function LibraryManager({open,onClose,onChange}:Props){
 const [documents,setDocuments]=useState<LibraryDocument[]>([]);
 const [selectedId,setSelectedId]=useState<string|null>(null);
 const [query,setQuery]=useState('');
 const [textValue,setTextValue]=useState('');
 const [originalText,setOriginalText]=useState('');
 const [pdfPage,setPdfPage]=useState(1);
 const [loading,setLoading]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [windowSize,setWindowSize]=useState<{width:number;height:number}|null>(null);
 const [windowPosition,setWindowPosition]=useState<{left:number;top:number}|null>(null);
 const moveStart=useRef<{x:number;y:number;left:number;top:number;width:number;height:number}|null>(null);
 const resizeStart=useRef<{x:number;y:number;width:number;height:number;left:number;top:number}|null>(null);
 const selected=documents.find(document=>document.id===selectedId);
 const filtered=useMemo(()=>documents.filter(document=>document.filename.toLowerCase().includes(query.toLowerCase())),[documents,query]);
 const dirty=selected&&textExtensions.has(extension(selected.filename))&&textValue!==originalText;

 const refresh=async(preferredId?:string)=>{
  const items=await api<LibraryDocument[]>('/api/library/documents');
  setDocuments(items);
  setSelectedId(current=>preferredId&&items.some(item=>item.id===preferredId)?preferredId:current&&items.some(item=>item.id===current)?current:items[0]?.id||null);
  onChange?.();
 };
 useEffect(()=>{if(!open)return;setLoading(true);setError('');void refresh().catch((cause:Error)=>setError(cause.message)).finally(()=>setLoading(false))},[open]);
 useEffect(()=>{setPdfPage(1);if(!open||!selected||!textExtensions.has(extension(selected.filename))){setTextValue('');setOriginalText('');return}let active=true;setError('');void api<{text:string}>(`/api/library/documents/${selected.id}/text`).then(data=>{if(active){setTextValue(data.text);setOriginalText(data.text)}}).catch((cause:Error)=>{if(active)setError(cause.message)});return()=>{active=false}},[open,selectedId]);
 useEffect(()=>{if(!open)return;const onKey=(event:KeyboardEvent)=>{if(event.key==='Escape')close()};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey)},[open,dirty]);
 const close=()=>{if(dirty&&!window.confirm('Discard unsaved text changes?'))return;onClose()};
 const choose=(id:string)=>{if(id===selectedId)return;if(dirty&&!window.confirm('Discard unsaved text changes?'))return;setSelectedId(id);setNotice('');setError('')};
 const upload=async(files:FileList|null)=>{if(!files?.length)return;setBusy(true);setError('');setNotice('');try{let lastId='';for(const file of Array.from(files)){const form=new FormData();form.append('file',file);const saved=await api<LibraryDocument>('/api/library/documents',{method:'POST',body:form});lastId=saved.id}await refresh(lastId);setNotice(`${files.length} file${files.length===1?'':'s'} added.`)}catch(cause:any){setError(cause.message)}finally{setBusy(false)}};
 const saveText=async()=>{if(!selected||!dirty)return;setBusy(true);setError('');setNotice('');try{await api<LibraryDocument>(`/api/library/documents/${selected.id}/text`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:textValue})});setOriginalText(textValue);await refresh(selected.id);setNotice('Text saved and search index updated.')}catch(cause:any){setError(cause.message)}finally{setBusy(false)}};
 const remove=async()=>{if(!selected)return;if(!window.confirm(`Delete ${selected.filename} from the local library?`))return;setBusy(true);setError('');setNotice('');try{await api<void>(`/api/library/documents/${selected.id}`,{method:'DELETE'});setSelectedId(null);await refresh();setNotice('File deleted.')}catch(cause:any){setError(cause.message)}finally{setBusy(false)}};
 const startMove=(event:ReactPointerEvent<HTMLElement>)=>{if(event.button!==0||(event.target as HTMLElement).closest('button'))return;const rect=event.currentTarget.parentElement!.getBoundingClientRect();moveStart.current={x:event.clientX,y:event.clientY,left:rect.left,top:rect.top,width:rect.width,height:rect.height};event.currentTarget.setPointerCapture(event.pointerId);event.preventDefault()};
 const move=(event:ReactPointerEvent<HTMLElement>)=>{const start=moveStart.current;if(!start)return;setWindowPosition({left:Math.max(0,Math.min(window.innerWidth-start.width,start.left+event.clientX-start.x)),top:Math.max(0,Math.min(window.innerHeight-start.height,start.top+event.clientY-start.y))})};
 const startResize=(event:ReactPointerEvent<HTMLButtonElement>)=>{const rect=event.currentTarget.parentElement!.getBoundingClientRect();resizeStart.current={x:event.clientX,y:event.clientY,width:rect.width,height:rect.height,left:rect.left,top:rect.top};event.currentTarget.setPointerCapture(event.pointerId);event.preventDefault()};
 const resize=(event:ReactPointerEvent<HTMLButtonElement>)=>{const start=resizeStart.current;if(!start)return;const maxWidth=window.innerWidth-start.left-12,maxHeight=window.innerHeight-start.top-12;setWindowSize({width:Math.max(Math.min(480,maxWidth),Math.min(maxWidth,start.width+event.clientX-start.x)),height:Math.max(Math.min(300,maxHeight),Math.min(maxHeight,start.height+event.clientY-start.y))})};
 if(!open)return null;
 const fileUrl=selected?publicApiUrl(`/api/library/documents/${selected.id}/file`):'';
 return createPortal(<div className="libraryManagerBackdrop" onMouseDown={event=>{if(event.target===event.currentTarget)close()}}>
  <section className="libraryManager" role="dialog" aria-modal="true" aria-label="Local library" style={{...windowSize,...windowPosition}}>
   <header onPointerDown={startMove} onPointerMove={move} onPointerUp={()=>{moveStart.current=null}} onPointerCancel={()=>{moveStart.current=null}}><div><strong>Local library</strong><span>{documents.length} resource{documents.length===1?'':'s'} · Drag the header to move · Resize from the lower right corner</span></div><button type="button" title="Close library" aria-label="Close library" onClick={close}><X size={21}/></button></header>
   <div className="libraryManagerToolbar"><label className="libraryManagerUpload"><FilePlus2 size={17}/>{busy?'Working…':'Add files'}<input type="file" multiple accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.jpg,.jpeg,.png,.mp3,.wav,.m4a,.ogg,.mp4,.webm,.mov" disabled={busy} onChange={event=>{void upload(event.target.files);event.target.value=''}}/></label><div className="libraryManagerSearch"><Search size={17}/><input aria-label="Find library resources" placeholder="Find a resource by name" value={query} onChange={event=>setQuery(event.target.value)}/></div></div>
   <div className="libraryManagerContent"><aside aria-label="Library resources">{loading?<p className="libraryManagerEmpty">Loading resources…</p>:filtered.length?filtered.map(document=><button type="button" key={document.id} className={`libraryManagerItem ${selectedId===document.id?'active':''}`} onClick={()=>choose(document.id)}>{icon(document.filename)}<span><strong title={document.filename}>{document.filename}</strong><small>{kind(document.filename)} · {document.passages?`${document.passages} searchable passage${document.passages===1?'':'s'}`:'Stored for viewing'}</small></span></button>):<p className="libraryManagerEmpty">{query?'No matching resources.':'No resources yet. Add a file to begin.'}</p>}</aside>
    <main>{selected?<><div className="libraryManagerDetailHeader"><div><strong title={selected.filename}>{selected.filename}</strong><small>{kind(selected.filename)} · Added {new Date(selected.uploaded_at).toLocaleDateString()}</small></div><div className="libraryManagerActions"><a href={fileUrl} target="_blank" rel="noreferrer" title="Open original file"><ExternalLink size={16}/> Open</a><button type="button" onClick={()=>void remove()} disabled={busy} title="Delete this resource"><Trash2 size={16}/> Delete</button></div></div>
     <div className="libraryManagerPreview">{kind(selected.filename)==='PDF'?<div className="libraryManagerPdf"><nav aria-label="PDF pages"><button type="button" onClick={()=>setPdfPage(page=>Math.max(1,page-1))} disabled={pdfPage<=1}>Previous</button><span>Page {pdfPage} of {Math.max(1,selected.pages)}</span><button type="button" onClick={()=>setPdfPage(page=>Math.min(selected.pages,page+1))} disabled={pdfPage>=selected.pages}>Next</button></nav><div><img src={publicApiUrl(`/api/library/documents/${selected.id}/pages/${pdfPage}/preview`)} alt={`${selected.filename}, page ${pdfPage}`}/></div></div>:kind(selected.filename)==='Image'?<img src={fileUrl} alt={selected.filename}/>:kind(selected.filename)==='Audio'?<div className="libraryManagerMedia"><Music2 size={40}/><audio controls preload="metadata" src={fileUrl}>Audio preview is unavailable in this browser.</audio></div>:kind(selected.filename)==='Video'?<video controls preload="metadata" src={fileUrl}>Video preview is unavailable in this browser.</video>:kind(selected.filename)==='Text'?<div className="libraryManagerEditor"><label htmlFor="libraryTextEditor">Edit text</label><textarea id="libraryTextEditor" value={textValue} onChange={event=>setTextValue(event.target.value)} spellCheck={false}/><div><span>{dirty?'Unsaved changes':'Saved text'}</span><button type="button" onClick={()=>void saveText()} disabled={!dirty||busy}><Save size={16}/> Save changes</button></div></div>:<div className="libraryManagerMedia"><File size={40}/><p>Open this file in a compatible application to view it.</p><a href={fileUrl} target="_blank" rel="noreferrer">Open file</a></div>}</div></>:<div className="libraryManagerEmpty">Select a resource to preview it.</div>}</main></div>
   {(error||notice)&&<div className={`libraryManagerStatus ${error?'error':''}`} role="status">{error||notice}</div>}<button type="button" className="libraryManagerResize" aria-label="Resize library window" title="Drag to resize width and height" onPointerDown={startResize} onPointerMove={resize} onPointerUp={()=>{resizeStart.current=null}} onPointerCancel={()=>{resizeStart.current=null}}><Grip size={20} aria-hidden="true"/></button>
  </section>
 </div>,document.body);
}
